#!/usr/bin/env python3
"""The review loop: CodeRabbit reviews a pull request, Claude answers its findings,
and a fixed set of rules says whether the result could merge without a person.

Three commands, each run by a workflow in ../workflows/:

  threads   list CodeRabbit's open findings on a pull request (for Claude to read)
  handover  label the pull request for a person when the rounds are used up
  apply     take the files Claude changed into a fresh checkout, commit, push, and
            answer each finding
  gate      decide whether the pull request may merge without a person, say why on
            the pull request, and merge it when the rules allow

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
RISKS = ["Minimal", "Low", "Moderate", "High", "Critical"]
DEFAULTS = {
    "mode": "dry-run",
    "merge_method": "squash",
    "max_fix_rounds": 2,
    "trusted_authors": [],
    "blocking_severities": ["Critical", "Major"],
    "protected_paths": [".github/*", ".coderabbit.yaml"],
    "areas": [{"name": "automation", "ceiling": None, "code": True, "paths": [".github/*", ".coderabbit.yaml"]},
              {"name": "everything else", "ceiling": 0, "code": True, "paths": ["*"]}],
    "default_area": "everything else",
    "scores": {"merge_risk": {"Minimal": 0}, "security_risk": {"Minimal": 0, "Low": 0, "not rated": 1},
               "size_lines": [500, 2000, 5000], "spread_many_files": 10},
    "size_ignored": [],
    "test_paths": [],
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
                "answered": any(ANSWERED in c["body"] for c in node["comments"]["nodes"][1:]),
                "declined": any(ANSWERED in c["body"] and c["body"].startswith("**Not changed**")
                                for c in node["comments"]["nodes"][1:])})
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

def open_findings(number, settings=None):
    """CodeRabbit's findings that are still open and that the loop has not answered yet.

    Findings on files Claude may not change (the automation itself) are left out: its
    edits there are undone, so those findings wait for a person.
    """
    protected = (settings or DEFAULTS)["protected_paths"]
    return [t for t in review_threads(number) if not t["resolved"] and not t["outdated"] and not t["answered"]
            and not any(fnmatch.fnmatch(t["path"] or "", pattern) for pattern in protected)]


def cmd_threads(args):
    settings = config(args.config)
    pull = api("repos/%s/pulls/%d" % (REPO, args.pr))
    same_repo = (pull["head"]["repo"] or {}).get("full_name") == REPO
    findings = open_findings(args.pr, settings)
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
    by_id = {thread["comment_id"]: thread for thread in open_findings(args.pr, settings)}
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
        if waiting > 0:  # only a person takes the label off again
            set_label(args.pr, True)


# --- gate ------------------------------------------------------------------
#
# Three layers, all read from merge-gate.json:
#   1. hard stops    any one sends the pull request to a person
#   2. a risk score  six factors, added up
#   3. a ceiling     each area of the repository merges only at or below its own
#                    score; a pull request uses the lowest ceiling it touches

def review_summary(number):
    """What CodeRabbit's summary comment says about the latest review."""
    found = {"merge": None, "security": None, "covered": None, "kind": None, "security_covered": None}
    comments = pages("repos/%s/issues/%d/comments?per_page=100" % (REPO, number))
    for item in reversed(comments):
        body = item["body"]
        if not is_reviewer(item["user"]["login"]) or "Merge Risk:" not in body:
            continue
        level = r"\*\*\W*(%s)\*\*(?:[^`\n]*`([0-9a-f]{5,40})`)?" % "|".join(RISKS)
        match = re.search(r"\*\*Merge Risk:\*\*\s*" + level, body)
        if match:
            found["merge"], found["covered"] = match.group(1), match.group(2)
        match = re.search(r"<!-- final_review_risk_coverage:(\{.*?\}) -->", body)
        if match:
            try:
                coverage = json.loads(match.group(1))
                found["covered"], found["kind"] = coverage.get("coveredCommitId"), coverage.get("kind")
            except ValueError:
                pass
        match = re.search(r"\*\*Security architecture risk:\*\*\s*" + level, body)
        if match:
            found["security"], found["security_covered"] = match.group(1), match.group(2)
        break
    return found


def find_pull(args):
    if args.pr:
        return args.pr
    sha = os.environ.get("HEAD_SHA", "")
    if not sha:
        return None
    pulls = api("repos/%s/commits/%s/pulls" % (REPO, sha)) or []
    numbers = [p["number"] for p in pulls if p["state"] == "open" and p["head"]["sha"] == sha]
    return numbers[0] if numbers else None


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def area_of(path, settings):
    for area in settings["areas"]:
        if matches(path, area["paths"]):
            return area
    return next(a for a in settings["areas"] if a["name"] == settings["default_area"])


def fingerprint(changes):
    """The changed files of a pull request, in a form two listings can be compared by."""
    return sorted((c["filename"], c.get("previous_filename") or "", c.get("sha") or "", c["status"],
                   c["additions"], c["deletions"]) for c in changes)


def covers(reviewed, sha):
    return bool(reviewed) and (sha.startswith(reviewed) or reviewed.startswith(sha))


def cmd_gate(args):
    settings = config(args.config)
    scores = settings["scores"]
    number = find_pull(args)
    if not number:
        print("no open pull request for this event; nothing to check")
        return
    pull = api("repos/%s/pulls/%d" % (REPO, number))
    if pull["state"] != "open":
        print("pull request %d is %s; nothing to check" % (number, pull["state"]))
        return
    sha = pull["head"]["sha"]
    base = pull["base"]["ref"]
    owner = REPO.split("/")[0]

    # CodeRabbit must have finished a real review of this exact commit. While it has
    # not, say so in the commit status and leave the comment alone.
    for attempt in range(4):
        runs = api("repos/%s/commits/%s/check-runs?per_page=100" % (REPO, sha))["check_runs"]
        review = [r for r in runs if r["app"]["slug"] == REVIEWER and r["name"] == "CodeRabbit"]
        summary = review_summary(number)
        done = bool(review) and review[0]["status"] == "completed"
        if done and covers(summary["covered"], sha):
            break
        if attempt < 3 and not args.no_wait:
            time.sleep(20)
    if not done:
        print("PR %d at %s: CodeRabbit has not finished; waiting" % (number, sha[:7]))
        if args.post:
            gh("api", "repos/%s/statuses/%s" % (REPO, sha), "-f", "state=pending", "-f", "context=merge-gate",
               "-f", "description=Waiting for CodeRabbit to finish its review", check=False)
        return

    # ---- layer 1: hard stops
    stops = []

    def stop(name, passed, detail):
        stops.append((name, bool(passed), detail))

    stop("Open and not a draft", not pull["draft"], "draft" if pull["draft"] else "open")
    # The owner's pull requests come from a branch here. A trusted author's may come
    # from their own copy of the repository: the gate never runs a pull request's code,
    # it only reads what GitHub and CodeRabbit report about it.
    author = pull["user"]["login"]
    trusted = author in settings["trusted_authors"]
    stop("Written by the owner or a trusted author", author == owner or trusted,
         "author is %s%s" % (author, " (trusted)" if trusted else ""))
    source = (pull["head"]["repo"] or {}).get("full_name")
    stop("Comes from this repository, or from a trusted author's copy", source == REPO or (trusted and bool(source)),
         source or "the source repository is gone")
    stop("Goes into the default branch", base == pull["base"]["repo"]["default_branch"], "goes into " + base)
    title = review[0]["output"]["title"] or ""
    stop("CodeRabbit finished its review",
         review[0]["conclusion"] == "success" and not re.search(r"rate|limit|skip|paus|cancel", title, re.I),
         "check: %s" % (title or review[0]["conclusion"]))
    current = covers(summary["covered"], sha) and summary["kind"] in (None, "reviewed")
    stop("The review covers the latest commit", current,
         "reviewed up to %s, latest is %s" % ((summary["covered"] or "nothing")[:7], sha[:7]))
    merge_level = summary["merge"] if current else None
    stop("Merge risk is not High or Critical", merge_level in scores["merge_risk"],
         "CodeRabbit says %s" % (merge_level or "nothing"))
    # No security rating at all reads as "not rated". A rating for an older commit is
    # not that: it may be High, so it stops the merge until CodeRabbit rates this commit.
    security_stale = bool(summary["security"]) and not covers(summary["security_covered"], sha)
    security_key = summary["security"] or "not rated"
    stop("Security risk is not High or Critical", not security_stale and security_key in scores["security_risk"],
         "CodeRabbit says %s%s" % (security_key, ", for an older commit" if security_stale else ""))

    threads = review_threads(number)
    unresolved = [t for t in threads if not t["resolved"]]
    blocking = [t for t in unresolved if t["severity"] in settings["blocking_severities"] + ["Unknown"]]
    stop("No open %s findings" % " or ".join(settings["blocking_severities"]), not blocking,
         "%d open" % len(blocking))

    loop_jobs = ("merge-gate", "claude", "apply")
    others = [r for r in runs if r["app"]["slug"] != REVIEWER and r["name"] not in loop_jobs]
    bad = [r["name"] for r in others if r["status"] != "completed"
           or r["conclusion"] not in ("success", "neutral", "skipped")]
    statuses = [s for s in api("repos/%s/commits/%s/status" % (REPO, sha))["statuses"] if s["context"] != "merge-gate"]
    bad += [s["context"] for s in statuses if s["state"] != "success"]
    ran = [r for r in others if r["conclusion"] == "success"] + [s for s in statuses if s["state"] == "success"]
    stop("Other checks pass", not bad, ", ".join(bad) or "%d other check(s), none failing" % (len(others) + len(statuses)))

    changes = pages("repos/%s/pulls/%d/files?per_page=100" % (REPO, number))
    # A renamed file counts under both names, so moving a file cannot hide it.
    files = sorted({name for change in changes for name in (change["filename"], change.get("previous_filename")) if name})
    areas = {path: area_of(path, settings) for path in files}
    never = sorted(path for path, area in areas.items() if area["ceiling"] is None)
    stop("No automation files changed", not never, ", ".join(never[:4]) or "none")

    rounds = fix_rounds(number)
    stop("At most %d rounds of fixes" % settings["max_fix_rounds"], rounds <= settings["max_fix_rounds"], "%d so far" % rounds)
    labels = [label["name"] for label in pull["labels"]]
    stop("Not handed to a person", LABEL not in labels, "label %s is set" % LABEL if LABEL in labels else "no label")
    for attempt in range(5):  # GitHub works this out a little after it is first asked
        if pull.get("mergeable") is not None or args.no_wait:
            break
        time.sleep(5)
        pull = api("repos/%s/pulls/%d" % (REPO, number))
    stop("No merge conflicts", pull.get("mergeable") is True,
         {True: "none", False: "conflicts with " + pull["base"]["ref"]}.get(pull.get("mergeable"), "GitHub has not worked it out"))

    # ---- layer 2: the risk score
    factors = []

    def factor(name, points, detail):
        factors.append((name, points, detail))

    factor("Merge risk", scores["merge_risk"].get(merge_level, 0), merge_level or "not rated")
    factor("Security risk", scores["security_risk"].get(security_key, 0), security_key)

    # Only a test file that is still there, with added lines, counts. Deleting or
    # moving tests away must not earn the discount.
    tests_changed = [change["filename"] for change in changes
                     if change["status"] != "removed" and change["additions"] > 0
                     and matches(change["filename"], settings["test_paths"])]
    if not ran:
        proof, proof_detail = 2, "nothing ran the code"
    elif tests_changed:
        proof, proof_detail = 0, "checks ran, and the change comes with tests"
    else:
        proof, proof_detail = 1, "checks ran, but no test changed with the code"

    code_files = [path for path in files if areas[path]["code"] and areas[path]["ceiling"] is not None]
    counted = {change["filename"]: change["additions"] + change["deletions"] for change in changes
               if change["filename"] in code_files and not matches(change["filename"], settings["size_ignored"])}
    lines = sum(counted.values())
    size = 0 if proof == 0 else sum(lines > limit for limit in scores["size_lines"])
    factor("Size", size, "%d code lines%s" % (lines, ", not counted because tests cover it" if proof == 0 and lines else ""))

    code_areas = sorted({areas[path]["name"] for path in code_files})
    if len(code_areas) > 1:
        spread, spread_detail = 2, "several areas: " + ", ".join(code_areas)
    elif len(code_files) > scores["spread_many_files"]:
        spread, spread_detail = 1, "%d code files in one area" % len(code_files)
    else:
        spread, spread_detail = 0, "%d code file(s) in %s" % (len(code_files), code_areas[0] if code_areas else "no code area")
    factor("Spread", spread, spread_detail)

    declined = [t for t in threads if t["declined"]]
    serious = [t for t in threads if t["severity"] in settings["blocking_severities"] + ["Unknown"]]
    if unresolved or declined:
        history, history_detail = 3, "%d finding(s) still open, %d not changed" % (len(unresolved), len(declined))
    elif serious or rounds >= 2:
        history, history_detail = 2, "%d serious finding(s) fixed, %d round(s) of fixes" % (len(serious), rounds)
    elif threads:
        history, history_detail = 1, "%d small finding(s), all fixed" % len(threads)
    else:
        history, history_detail = 0, "clean first review"
    factor("Review history", history, history_detail)
    factor("Proof", proof, proof_detail)
    score = sum(points for _, points, _ in factors)

    # ---- layer 3: the ceiling of the strictest area touched
    touched = [area for area in settings["areas"] if area["ceiling"] is not None
               and any(areas[path] is area for path in files)]
    strictest = min(touched, key=lambda area: area["ceiling"]) if touched else None
    within = strictest is not None and score <= strictest["ceiling"]
    ceiling_text = "strictest area touched is **%s**, which merges at %d or less" % (
        strictest["name"], strictest["ceiling"]) if strictest else "no area that may merge was touched"

    passed = all(ok for _, ok, _ in stops) and within
    merging = settings["mode"] == "merge"
    verdict = ("merging" if merging else "would merge") if passed else "needs a person"
    print("PR %d at %s: %s (score %d; %s)" % (number, sha[:7], verdict, score, ceiling_text.replace("*", "")))
    for name, ok, detail in stops:
        print("  %s %s: %s" % ("PASS" if ok else "STOP", name, detail))
    for name, points, detail in factors:
        print("  +%d %s: %s" % (points, name, detail))
    if not args.post:
        return

    changed_mind = None
    if passed and merging:
        # The checks above took a while. Look once more for a reason to stop that a
        # person may have given in the meantime; the merge itself is tied to this commit.
        latest = api("repos/%s/pulls/%d" % (REPO, number))
        if latest["state"] != "open" or latest["draft"]:
            changed_mind = "it is no longer open and ready"
        elif latest["head"]["sha"] != sha:
            changed_mind = "it got a new commit"
        elif latest["base"]["ref"] != base:
            changed_mind = "it was pointed at %s instead of %s" % (latest["base"]["ref"], base)
        elif fingerprint(pages("repos/%s/pulls/%d/files?per_page=100" % (REPO, number))) != fingerprint(changes):
            changed_mind = "its changed files are no longer the ones that were scored"
        elif LABEL in [label["name"] for label in latest["labels"]]:
            changed_mind = "the label %s was added" % LABEL
    if changed_mind:
        passed, verdict = False, "needs a person"

    # The status is written only now, after the last look, so a green status always
    # means every check finished. It still goes before the merge: the branch rule on
    # the default branch asks for it.
    gh("api", "repos/%s/statuses/%s" % (REPO, sha), "-f", "state=" + ("success" if passed else "failure"),
       "-f", "context=merge-gate", "-f", "description=" + ("Score %d: %s" % (score, verdict))[:140], check=False)
    if changed_mind:
        outcome = "Passed the rules, but while it was checked %s." % changed_mind
    elif passed and merging:
        result = subprocess.run(["gh", "pr", "merge", str(number), "--repo", REPO, "--" + settings["merge_method"],
                                 "--match-head-commit", sha], capture_output=True, text=True)
        if result.returncode == 0:
            verdict, outcome = "merged", "Merged by the gate."
        else:
            verdict = "passed, but GitHub refused the merge"
            reason = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "no reason given"
            outcome = "GitHub said: `%s`" % harmless(reason, 300).replace("`", "'")
    elif passed:
        outcome = "The gate is set to report only (`mode` in `.github/merge-gate.json`); nothing was merged."
    else:
        outcome = "Left for a person."

    stop_rows = "\n".join("| %s | %s | %s |" % ("✅" if ok else "❌", name, detail.replace("|", "/")) for name, ok, detail in stops)
    factor_rows = "\n".join("| %s | %d | %s |" % (name, points, detail.replace("|", "/")) for name, points, detail in factors)
    body = ("%s\n**Merge gate: %s.** Checked at `%s`.\n\n"
            "**Risk score %d.** The %s.\n\n| Factor | Points | Found |\n|---|---|---|\n%s\n\n"
            "<details><summary>Hard stops: %s</summary>\n\n| | Rule | Found |\n|---|---|---|\n%s\n\n</details>\n\n%s"
            % (MARK, verdict, sha[:7], score, ceiling_text, factor_rows,
               "all clear" if all(ok for _, ok, _ in stops) else "%d hit" % sum(not ok for _, ok, _ in stops),
               stop_rows, outcome))
    mine = [c for c in pages("repos/%s/issues/%d/comments?per_page=100" % (REPO, number)) if MARK in c["body"]]
    if mine:
        gh("api", "-X", "PATCH", "repos/%s/issues/comments/%d" % (REPO, mine[-1]["id"]), "-f", "body=" + body)
    else:
        comment(number, body)


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
