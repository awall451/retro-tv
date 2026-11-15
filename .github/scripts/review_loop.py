#!/usr/bin/env python3
"""The review loop: CodeRabbit reviews a pull request, Claude answers its findings,
and a fixed set of rules says whether the result could merge without a person.

Three commands, each run by a workflow in ../workflows/:

  threads   list CodeRabbit's open findings on a pull request (for Claude to read)
  handover  label the pull request for a person when the rounds are used up
  apply     take the files Claude changed into a fresh checkout, commit, push, and
            answer each finding
  gate      check the merge rules and report the result on the pull request

Claude runs in a job of its own whose token can only read. What it leaves behind (its
files and its answers) is treated as untrusted: `apply` runs in a second job, starts
from a fresh checkout, takes only file contents from Claude's job, and looks the
findings up again itself.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tarfile
import time

REPO = os.environ.get("GITHUB_REPOSITORY", "")
REVIEWER = "coderabbitai"
LABEL = "needs-human"
MARK = "<!-- merge-gate -->"
ANSWERED = "(review loop, round "
SCRATCH = ".review-loop"
TREE_LIMIT = 300 * 1024 * 1024  # most that is taken from Claude's job, in bytes
TRAILER = "Fix-Round:"
SEVERITIES = ["Critical", "Major", "Minor", "Trivial", "Info"]
DEFAULTS = {
    "max_fix_rounds": 2,
    "allowed_merge_risk": ["Minimal", "Low"],
    "blocking_severities": ["Critical", "Major"],
    "protected_paths": [".github/*", ".coderabbit.yaml"],
    "auto_merge_paths": [],
}


def gh(*args, data=None, check=True):
    result = subprocess.run(["gh", *args], input=data, capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit("gh %s failed: %s" % (" ".join(args[:3]), result.stderr.strip()[-400:]))
    return result.stdout


def api(path, *args, check=True):
    out = gh("api", path, *args, check=check)
    return json.loads(out) if out.strip() else None


def pages(path):
    """Every item of a listing that comes in pages."""
    return [item for page in json.loads(gh("api", "--paginate", "--slurp", path)) for item in page]


def config(path):
    settings = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            settings.update(json.load(handle))
    return settings


def is_reviewer(login):
    return (login or "").replace("[bot]", "") == REVIEWER


def plain(text):
    """A comment's text without the markup CodeRabbit wraps around it."""
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def severity(text):
    match = re.search(r"\*\*\s*(%s)\*\*" % "|".join(SEVERITIES), text)
    return match.group(1) if match else "Unknown"


def review_threads(number):
    """CodeRabbit's review threads on a pull request, resolved or not."""
    owner, name = REPO.split("/")
    query = """
    query($owner: String!, $name: String!, $number: Int!, $after: String) {
      repository(owner: $owner, name: $name) { pullRequest(number: $number) {
        reviewThreads(first: 50, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes { id isResolved isOutdated path line originalLine
                  comments(first: 30) { nodes { databaseId body author { login } } } } } } } }"""
    found, after = [], None
    while True:
        args = ["api", "graphql", "-f", "query=" + query, "-f", "owner=" + owner, "-f", "name=" + name,
                "-F", "number=%d" % number]
        if after:
            args += ["-f", "after=" + after]
        data = json.loads(gh(*args))["data"]["repository"]["pullRequest"]["reviewThreads"]
        for node in data["nodes"]:
            first = (node["comments"]["nodes"] or [None])[0]
            if not first or not is_reviewer((first.get("author") or {}).get("login")):
                continue
            text = plain(first["body"])
            found.append({
                "comment_id": first["databaseId"], "path": node["path"],
                "line": node["line"] or node["originalLine"], "resolved": node["isResolved"],
                "outdated": node["isOutdated"], "severity": severity(text), "text": text[:6000],
                "answered": any(ANSWERED in c["body"] for c in node["comments"]["nodes"][1:])})
        if not data["pageInfo"]["hasNextPage"]:
            return found
        after = data["pageInfo"]["endCursor"]


def fix_rounds(number):
    commits = pages("repos/%s/pulls/%d/commits?per_page=100" % (REPO, number))
    return sum(TRAILER in commit["commit"]["message"] for commit in commits)


def comment(number, body):
    gh("api", "repos/%s/issues/%d/comments" % (REPO, number), "-f", "body=" + body)


def set_label(number, wanted):
    labels = [label["name"] for label in api("repos/%s/issues/%d/labels" % (REPO, number))]
    if wanted and LABEL not in labels:
        gh("api", "repos/%s/labels" % REPO, "-f", "name=" + LABEL, "-f", "color=d93f0b",
           "-f", "description=The review loop stopped; a person has to look", check=False)
        gh("api", "repos/%s/issues/%d/labels" % (REPO, number), "-f", "labels[]=" + LABEL)
    elif not wanted and LABEL in labels:
        gh("api", "-X", "DELETE", "repos/%s/issues/%d/labels/%s" % (REPO, number, LABEL), check=False)


def output(**values):
    target = os.environ.get("GITHUB_OUTPUT")
    for key, value in values.items():
        print("%s=%s" % (key, value))
        if target:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write("%s=%s\n" % (key, value))


# --- threads ---------------------------------------------------------------

def open_findings(number):
    """CodeRabbit's findings that are still open and that the loop has not answered yet."""
    return [t for t in review_threads(number) if not t["resolved"] and not t["outdated"] and not t["answered"]]


def cmd_threads(args):
    settings = config(args.config)
    pull = api("repos/%s/pulls/%d" % (REPO, args.pr))
    same_repo = (pull["head"]["repo"] or {}).get("full_name") == REPO
    findings = open_findings(args.pr)
    rounds = fix_rounds(args.pr)
    limit = settings["max_fix_rounds"]
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"pr": args.pr, "round": rounds + 1, "max_rounds": limit, "threads": findings}, handle, indent=1)
    workable = pull["state"] == "open" and same_repo and bool(findings)
    output(proceed=str(workable and rounds < limit).lower(), handover=str(workable and rounds >= limit).lower(),
           count=len(findings), round=rounds + 1, head_ref=pull["head"]["ref"], head_sha=pull["head"]["sha"])


def cmd_handover(args):
    findings, rounds = open_findings(args.pr), fix_rounds(args.pr)
    set_label(args.pr, True)
    comment(args.pr, "The review loop has made %d round(s) of fixes and CodeRabbit still has %d open "
                     "finding(s). It stops here; a person has to look." % (rounds, len(findings)))


# --- apply -----------------------------------------------------------------

def git(*args, check=True):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit("git %s failed: %s" % (args[0], result.stderr.strip()[-400:]))
    return result.stdout


def changed_files():
    """Paths that differ from the last commit, old names of renamed files included."""
    fields = git("status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    paths, index = [], 0
    while index < len(fields) and fields[index]:
        status, path = fields[index][:2], fields[index][3:]
        paths.append(path)
        if "R" in status or "C" in status:  # with -z the old name follows as its own field
            index += 1
            paths.append(fields[index])
        index += 1
    return paths


def take_tree(archive_path):
    """Make the checkout's files match the tree Claude's job packed.

    Only regular files are taken. Links, anything named .git, the loop's scratch folder
    and compiled Python are left out, and Python's own checks refuse paths that would
    land outside the checkout.
    """
    for path in filter(None, git("ls-files", "-z").split("\0")):
        if os.path.isfile(path) and not os.path.islink(path):
            os.remove(path)
    taken = 0
    with tarfile.open(archive_path) as archive:
        for member in archive:
            parts = [part for part in member.name.split("/") if part not in ("", ".")]
            if not parts or not member.isfile():
                continue
            if ".git" in parts or parts[0] == SCRATCH or "__pycache__" in parts or parts[-1].endswith(".pyc"):
                continue
            taken += member.size
            if taken > TREE_LIMIT:
                sys.exit("the tree from Claude's job is larger than %d bytes" % TREE_LIMIT)
            try:
                archive.extract(member, ".", filter="data")
            except tarfile.FilterError as problem:
                print("left out:", problem)


def harmless(text, limit):
    """Text from Claude, made safe to post: no mention can call a person or a bot."""
    return (text or "").strip()[:limit].replace("@", "@\u200b")


def cmd_apply(args):
    settings = config(args.config)
    pull = api("repos/%s/pulls/%d" % (REPO, args.pr))
    rounds, limit = fix_rounds(args.pr), settings["max_fix_rounds"]
    this_round = rounds + 1
    by_id = {thread["comment_id"]: thread for thread in open_findings(args.pr)}
    try:
        result = json.loads(os.environ.get("CLAUDE_RESULT") or "{}")
    except ValueError:
        result = {}
    if not isinstance(result, dict):
        result = {}
    words = {"fixed": "Fixed", "declined": "Not changed", "needs_human": "Needs a person"}
    answers, seen = [], set()
    for answer in result.get("threads") or []:
        key = answer.get("comment_id") if isinstance(answer, dict) else None
        if key in by_id and key not in seen and answer.get("verdict") in words:
            seen.add(key)
            answers.append(answer)

    moved = git("rev-parse", "HEAD").strip() != args.head_sha or pull["head"]["sha"] != args.head_sha
    files = []
    if moved:
        print("the branch moved while Claude worked; its changes are not used")
    elif rounds < limit:
        take_tree(args.tree)
        # Claude must not change the automation that checks its own work.
        for path in changed_files():
            if any(fnmatch.fnmatch(path, pattern) for pattern in settings["protected_paths"]):
                print("undoing a change to a protected path:", path)
                git("checkout", "--", path, check=False)
                git("clean", "-fdq", "--", path, check=False)
        files = changed_files()

    fixed = [a for a in answers if a["verdict"] == "fixed"]
    pushed = False
    if files and fixed:
        subject = re.sub(r"\s+", " ", str(result.get("commit_subject") or "")).strip()[:100] \
            or "review: fixes for CodeRabbit's findings"
        body = "\n".join("- %s:%s" % (by_id[a["comment_id"]]["path"], by_id[a["comment_id"]]["line"])
                         for a in fixed)
        message = "%s\n\nAnswers CodeRabbit's review findings on:\n%s\n\n%s %d\n" \
                  "Co-Authored-By: Claude <noreply@anthropic.com>\n" % (subject, body, TRAILER, this_round)
        if args.dry_run:
            print("would commit %d file(s): %s\n%s" % (len(files), ", ".join(files[:8]), message))
        else:
            git("add", "-A")
            git("-c", "core.hooksPath=/dev/null", "-c", "user.name=claude[bot]",
                "-c", "user.email=41898282+claude[bot]@users.noreply.github.com", "commit", "-q", "-m", message)
            helper = "!f() { echo username=x-access-token; echo password=$GH_TOKEN; }; f"
            git("-c", "credential.helper=", "-c", "credential.helper=" + helper, "push", "-q",
                "https://github.com/%s.git" % REPO, "HEAD:refs/heads/" + pull["head"]["ref"])
            pushed = True
    elif files:
        print("files changed but no finding was marked fixed; nothing is committed")

    for answer in answers:
        if answer["verdict"] == "fixed" and not (pushed or args.dry_run):
            continue
        text = "**%s** %s%d). %s" % (words[answer["verdict"]], ANSWERED, this_round, harmless(answer.get("reply"), 3000))
        if args.dry_run:
            print("would reply on %d: %s" % (answer["comment_id"], text[:160]))
        else:
            gh("api", "repos/%s/pulls/%d/comments/%d/replies" % (REPO, args.pr, answer["comment_id"]),
               "-f", "body=" + text, check=False)

    counts = {key: sum(a["verdict"] == key for a in answers) for key in words}
    if not (pushed or args.dry_run):
        counts["fixed"] = 0
    waiting = len(by_id) - counts["fixed"] - counts["declined"]
    note = " The branch moved while Claude worked, so its changes were not used." if moved else \
        ("" if answers else " The run produced no answers.")
    summary = "**Review loop, round %d of %d.** %d finding(s): %d fixed, %d not changed, %d need a person.%s\n\n%s" % (
        this_round, limit, len(by_id), counts["fixed"], counts["declined"], waiting, note,
        harmless(result.get("summary"), 2000))
    if args.dry_run:
        print(summary, "\nlabel:", waiting > 0)
    else:
        comment(args.pr, summary)
        set_label(args.pr, waiting > 0)


# --- gate ------------------------------------------------------------------

def merge_risk(number):
    """(level, commit prefix) from CodeRabbit's latest summary comment, or (None, None)."""
    comments = pages("repos/%s/issues/%d/comments?per_page=100" % (REPO, number))
    for item in reversed(comments):
        if not is_reviewer(item["user"]["login"]):
            continue
        match = re.search(r"\*\*Merge Risk:\*\*\s*\*\*\W*(Minimal|Low|Moderate|High|Critical)\*\*"
                          r"(?:[^`\n]*`([0-9a-f]{5,40})`)?", item["body"])
        if match:
            return match.group(1), match.group(2)
    return None, None


def find_pull(args):
    if args.pr:
        return args.pr
    sha = os.environ.get("HEAD_SHA", "")
    if not sha:
        return None
    pulls = api("repos/%s/commits/%s/pulls" % (REPO, sha)) or []
    numbers = [p["number"] for p in pulls if p["state"] == "open" and p["head"]["sha"] == sha]
    return numbers[0] if numbers else None


def cmd_gate(args):
    settings = config(args.config)
    number = find_pull(args)
    if not number:
        print("no open pull request for this event; nothing to check")
        return
    pull = api("repos/%s/pulls/%d" % (REPO, number))
    sha = pull["head"]["sha"]
    owner = REPO.split("/")[0]
    rules = []

    def rule(name, passed, detail):
        rules.append((name, bool(passed), detail))

    rule("Open and not a draft", pull["state"] == "open" and not pull["draft"],
         "draft" if pull["draft"] else pull["state"])
    rule("Written by the repository owner", pull["user"]["login"] == owner, "author is " + pull["user"]["login"])
    rule("Branch is in this repository", (pull["head"]["repo"] or {}).get("full_name") == REPO,
         (pull["head"]["repo"] or {}).get("full_name") or "deleted fork")

    # CodeRabbit must have finished a real review of this exact commit.
    for attempt in range(4):
        runs = api("repos/%s/commits/%s/check-runs?per_page=100" % (REPO, sha))["check_runs"]
        review = [r for r in runs if r["app"]["slug"] == REVIEWER and r["name"] == "CodeRabbit"]
        level, reviewed = merge_risk(number)
        if review and review[0]["status"] == "completed" and reviewed and sha.startswith(reviewed):
            break
        if attempt < 3 and not args.no_wait:
            time.sleep(20)
    title = (review[0]["output"]["title"] or "") if review else ""
    finished = bool(review) and review[0]["status"] == "completed" and review[0]["conclusion"] == "success" \
        and not re.search(r"rate|limit|skip|paus|cancel", title, re.I)
    rule("CodeRabbit finished its review", finished,
         "check: %s" % (title or (review[0]["status"] if review else "no CodeRabbit check on this commit")))
    current = bool(reviewed) and sha.startswith(reviewed)
    rule("The review covers the latest commit", current,
         "reviewed up to %s, latest is %s" % (reviewed or "nothing", sha[:7]))
    rule("Merge risk is %s" % " or ".join(settings["allowed_merge_risk"]),
         current and level in settings["allowed_merge_risk"], "CodeRabbit says %s" % (level or "nothing"))

    threads = [t for t in review_threads(number) if not t["resolved"]]
    blocking = [t for t in threads if t["severity"] in settings["blocking_severities"] + ["Unknown"]]
    rule("No open %s findings" % " or ".join(settings["blocking_severities"]), not blocking,
         "%d open (%d open findings in all)" % (len(blocking), len(threads)))

    others = [r for r in runs if r["app"]["slug"] != REVIEWER and r["name"] not in ("merge-gate", "coderabbit-fix")]
    bad = [r["name"] for r in others if r["status"] != "completed"
           or r["conclusion"] not in ("success", "neutral", "skipped")]
    statuses = api("repos/%s/commits/%s/status" % (REPO, sha))["statuses"]
    bad += [s["context"] for s in statuses if s["context"] != "merge-gate" and s["state"] != "success"]
    rule("Other checks pass", not bad, ", ".join(bad) or "%d other check(s), none failing" % (len(others) + len(statuses)))

    changes = pages("repos/%s/pulls/%d/files?per_page=100" % (REPO, number))
    # A renamed file counts under both names, so moving a file cannot hide it.
    files = sorted({name for change in changes for name in (change["filename"], change.get("previous_filename")) if name})

    def matches(path, patterns):
        return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)

    protected = [f for f in files if matches(f, settings["protected_paths"])]
    rule("No protected files changed", not protected, ", ".join(protected[:5]) or "none")
    if settings["auto_merge_paths"]:
        outside = [f for f in files if not matches(f, settings["auto_merge_paths"])]
        rule("Only files that may merge unattended (%s)" % ", ".join(settings["auto_merge_paths"]), not outside,
             ("%d outside, such as %s" % (len(outside), ", ".join(outside[:3]))) if outside else "all %d" % len(files))

    rounds = fix_rounds(number)
    rule("At most %d rounds of fixes" % settings["max_fix_rounds"], rounds <= settings["max_fix_rounds"], "%d so far" % rounds)
    labels = [label["name"] for label in pull["labels"]]
    rule("Not handed to a person", LABEL not in labels, "label %s is set" % LABEL if LABEL in labels else "no label")
    for attempt in range(5):  # GitHub works this out a little after it is first asked
        if pull.get("mergeable") is not None or args.no_wait:
            break
        time.sleep(5)
        pull = api("repos/%s/pulls/%d" % (REPO, number))
    rule("No merge conflicts", pull.get("mergeable") is True,
         {True: "none", False: "conflicts with " + pull["base"]["ref"]}.get(pull.get("mergeable"), "GitHub has not worked it out"))

    passed = all(ok for _, ok, _ in rules)
    verdict = "would merge" if passed else "needs a person"
    lines = ["%s %s: %s" % ("PASS" if ok else "FAIL", name, detail) for name, ok, detail in rules]
    print("PR %d at %s: %s\n  %s" % (number, sha[:7], verdict, "\n  ".join(lines)))
    if not args.post:
        return
    table = "\n".join("| %s | %s | %s |" % ("✅" if ok else "❌", name, detail.replace("|", "/"))
                      for name, ok, detail in rules)
    body = ("%s\n**Merge gate (dry run): %s.** Checked at `%s`.\n\n| | Rule | Found |\n|---|---|---|\n%s\n\n"
            "Nothing is merged by this check yet. It only reports."
            % (MARK, verdict, sha[:7], table))
    mine = [c for c in pages("repos/%s/issues/%d/comments?per_page=100" % (REPO, number)) if MARK in c["body"]]
    if mine:
        gh("api", "-X", "PATCH", "repos/%s/issues/comments/%d" % (REPO, mine[-1]["id"]), "-f", "body=" + body)
    else:
        comment(number, body)
    gh("api", "repos/%s/statuses/%s" % (REPO, sha), "-f", "state=" + ("success" if passed else "failure"),
       "-f", "context=merge-gate", "-f", "description=" + ("Dry run: " + verdict)[:140], check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "merge-gate.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    threads = commands.add_parser("threads")
    threads.add_argument("--pr", type=int, required=True)
    threads.add_argument("--out", required=True)
    threads.set_defaults(run=cmd_threads)
    handover = commands.add_parser("handover")
    handover.add_argument("--pr", type=int, required=True)
    handover.set_defaults(run=cmd_handover)
    apply = commands.add_parser("apply")
    apply.add_argument("--pr", type=int, required=True)
    apply.add_argument("--tree", required=True, help="tar file of the tree from Claude's job")
    apply.add_argument("--head-sha", required=True, help="the commit Claude's job started from")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(run=cmd_apply)
    gate = commands.add_parser("gate")
    gate.add_argument("--pr", type=int, default=int(os.environ.get("PR_INPUT") or 0))
    gate.add_argument("--post", action="store_true")
    gate.add_argument("--no-wait", action="store_true")
    gate.set_defaults(run=cmd_gate)
    args = parser.parse_args()
    if not REPO:
        sys.exit("GITHUB_REPOSITORY is not set")
    args.run(args)


if __name__ == "__main__":
    main()
