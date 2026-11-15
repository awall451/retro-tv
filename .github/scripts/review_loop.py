#!/usr/bin/env python3
"""The review loop: CodeRabbit reviews a pull request, Claude answers its findings,
and a fixed set of rules says whether the result could merge without a person.

Three commands, each run by a workflow in ../workflows/:

  threads   list CodeRabbit's open findings on a pull request (for Claude to read)
  apply     commit and push what Claude changed, and answer each finding
  gate      check the merge rules and report the result on the pull request

Everything goes through the `gh` program with the workflow's own token. Claude itself
gets no GitHub access: it reads the findings from a file and edits files, nothing else.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import time

REPO = os.environ.get("GITHUB_REPOSITORY", "")
REVIEWER = "coderabbitai"
LABEL = "needs-human"
MARK = "<!-- merge-gate -->"
ANSWERED = "(review loop, round "
SCRATCH = ".review-loop"
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

def cmd_threads(args):
    settings = config(args.config)
    pull = api("repos/%s/pulls/%d" % (REPO, args.pr))
    same_repo = (pull["head"]["repo"] or {}).get("full_name") == REPO
    # Findings the loop already answered are not handed to Claude a second time.
    open_threads = [t for t in review_threads(args.pr)
                    if not t["resolved"] and not t["outdated"] and not t["answered"]]
    rounds = fix_rounds(args.pr)
    limit = settings["max_fix_rounds"]
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"pr": args.pr, "head_ref": pull["head"]["ref"], "head_sha": pull["head"]["sha"],
                   "round": rounds + 1, "max_rounds": limit, "threads": open_threads}, handle, indent=1)
    proceed = pull["state"] == "open" and same_repo and bool(open_threads) and rounds < limit
    if open_threads and same_repo and rounds >= limit and not args.dry_run:
        set_label(args.pr, True)
        comment(args.pr, "The review loop has made %d rounds of fixes and CodeRabbit still has %d open "
                         "finding(s). It stops here; a person has to look." % (rounds, len(open_threads)))
    output(proceed=str(proceed).lower(), count=len(open_threads), round=rounds + 1, head_ref=pull["head"]["ref"])


# --- apply -----------------------------------------------------------------

def git(*args, check=True):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit("git %s failed: %s" % (args[0], result.stderr.strip()[-400:]))
    return result.stdout


def changed_files():
    """Paths changed in the checkout, leaving out the loop's own scratch folder."""
    paths = [line[3:].split(" -> ")[-1].strip('"') for line in git("status", "--porcelain").splitlines()]
    return [path for path in paths if not path.startswith(SCRATCH + "/")]


def cmd_apply(args):
    settings = config(args.config)
    with open(args.threads, encoding="utf-8") as handle:
        known = json.load(handle)
    by_id = {thread["comment_id"]: thread for thread in known["threads"]}
    try:
        result = json.loads(os.environ.get("CLAUDE_RESULT") or "{}")
    except ValueError:
        result = {}
    answers = [a for a in result.get("threads", []) if a.get("comment_id") in by_id]

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
        subject = re.sub(r"\s+", " ", result.get("commit_subject") or "").strip()[:100] \
            or "review: fixes for CodeRabbit's findings"
        body = "\n".join("- %s:%s" % (by_id[a["comment_id"]]["path"], by_id[a["comment_id"]]["line"])
                         for a in fixed)
        message = "%s\n\nAnswers CodeRabbit's review findings on:\n%s\n\n%s %d\n" \
                  "Co-Authored-By: Claude <noreply@anthropic.com>\n" % (subject, body, TRAILER, known["round"])
        if args.dry_run:
            print("would commit %d file(s):\n%s" % (len(files), message))
        else:
            git("add", "-A", "--", ".", ":!" + SCRATCH)
            git("-c", "user.name=claude[bot]", "-c", "user.email=41898282+claude[bot]@users.noreply.github.com",
                "commit", "-q", "-m", message)
            helper = "!f() { echo username=x-access-token; echo password=$GH_TOKEN; }; f"
            git("-c", "credential.helper=", "-c", "credential.helper=" + helper, "push", "-q",
                "https://github.com/%s.git" % REPO, "HEAD:refs/heads/" + known["head_ref"])
            pushed = True
    elif files:
        print("files changed but no finding was marked fixed; nothing is committed")
        git("checkout", "--", ".", check=False)

    words = {"fixed": "Fixed", "declined": "Not changed", "needs_human": "Needs a person"}
    for answer in answers:
        if answer["verdict"] == "fixed" and not (pushed or args.dry_run):
            continue
        text = "**%s** %s%d). %s" % (words.get(answer["verdict"], answer["verdict"]), ANSWERED,
                                     known["round"], answer.get("reply", "").strip()[:3000])
        if args.dry_run:
            print("would reply on %d: %s" % (answer["comment_id"], text[:160]))
        else:
            gh("api", "repos/%s/pulls/%d/comments/%d/replies" % (REPO, args.pr, answer["comment_id"]),
               "-f", "body=" + text, check=False)

    unanswered = len(by_id) - len(answers)
    stuck = unanswered > 0 or any(a["verdict"] == "needs_human" for a in answers)
    counts = {key: sum(a["verdict"] == key for a in answers) for key in words}
    if not (pushed or args.dry_run):
        counts["fixed"] = 0
    summary = "**Review loop, round %d of %d.** %d finding(s): %d fixed, %d not changed, %d need a person%s.\n\n%s" % (
        known["round"], known["max_rounds"], len(by_id), counts["fixed"], counts["declined"],
        counts["needs_human"] + unanswered, "" if answers else " (the run produced no answers)",
        (result.get("summary") or "").strip()[:2000])
    if args.dry_run:
        print(summary, "\nlabel:", stuck)
    else:
        comment(args.pr, summary)
        set_label(args.pr, stuck)


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

    files = [f["filename"] for f in pages("repos/%s/pulls/%d/files?per_page=100" % (REPO, number))]

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
    rule("No merge conflicts", pull.get("mergeable") is not False,
         {True: "none", False: "conflicts with " + pull["base"]["ref"]}.get(pull.get("mergeable"), "not worked out yet"))

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
    threads.add_argument("--dry-run", action="store_true")
    threads.set_defaults(run=cmd_threads)
    apply = commands.add_parser("apply")
    apply.add_argument("--pr", type=int, required=True)
    apply.add_argument("--threads", required=True)
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
