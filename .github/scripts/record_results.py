"""Turn a 'Quiz results:' issue into updates of courses/<course>/mistakes.json.

mistakes.json is a list of {id, domain, q, answer, lastPicked, misses,
firstMissed, lastMissed, status: open|resolved, resolvedOn}.
id is "<quiz date>#<question index>". Homework questions carry
"reviewOf": <id>, so answering one updates the original mistake.
"""
import datetime, json, os, re, sys
from pathlib import Path

body = os.environ.get("ISSUE_BODY", "")
m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S)
if not m:
    sys.exit("No ```json block in issue body")
data = json.loads(m.group(1))

course = data["course"]
if not re.fullmatch(r"[A-Za-z0-9._-]+", course):
    sys.exit(f"Bad course id: {course!r}")
cdir = Path("courses") / course
if not cdir.is_dir():
    sys.exit(f"Unknown course {course}")

quiz_id = str(data.get("quiz", ""))
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}|random", quiz_id):
    sys.exit(f"Bad quiz id: {quiz_id!r}")
score, total = int(data.get("score", 0)), int(data.get("total", 0))
today = datetime.date.today().isoformat()
mpath = cdir / "mistakes.json"
mistakes = json.loads(mpath.read_text()) if mpath.exists() else []
by_id = {x["id"]: x for x in mistakes}
quizzes = {}

def question(qid):
    date, idx = qid.split("#")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None
    if date not in quizzes:
        f = cdir / f"{date}.json"
        quizzes[date] = json.loads(f.read_text()) if f.exists() else None
    qz = quizzes[date]
    i = int(idx)
    return qz["questions"][i] if qz and 0 <= i < len(qz["questions"]) else None

new, again, fixed = [], [], []
for r in data.get("results", []):
    q = question(r["id"])
    if q is None:
        continue
    target = q.get("reviewOf") or r["id"]
    orig = question(target) or q
    item = by_id.get(target)
    if not r["ok"]:
        picked = [q["options"][p] for p in r.get("picked", []) if isinstance(p, int) and 0 <= p < len(q["options"])]
        if item is None:
            item = {"id": target, "domain": orig.get("domain"), "q": orig["q"],
                    "answer": [orig["options"][a] for a in orig["answer"]],
                    "misses": 0, "firstMissed": today, "status": "open"}
            mistakes.append(item); by_id[target] = item; new.append(item)
        else:
            (again if item["status"] == "open" else new).append(item)
        item.update(misses=item["misses"] + 1, lastMissed=today, lastPicked=picked, status="open")
        item.pop("resolvedOn", None)
    elif item and item["status"] == "open":
        item.update(status="resolved", resolvedOn=today)
        fixed.append(item)

mpath.write_text(json.dumps(mistakes, indent=1, ensure_ascii=False) + "\n")

open_n = sum(x["status"] == "open" for x in mistakes)
short = lambda x: f"- **{x['domain']}**: {x['q'][:110]}{'…' if len(x['q']) > 110 else ''}"
lines = [f"Recorded **{score}/{total}** for `{course}` {quiz_id}.", ""]
if new:   lines += [f"**New mistakes ({len(new)})** → homework in upcoming quizzes:"] + [short(x) for x in new] + [""]
if again: lines += [f"**Missed again ({len(again)})** → stays on the homework list:"] + [short(x) for x in again] + [""]
if fixed: lines += [f"**Fixed ({len(fixed)})** ✅ removed from homework:"] + [short(x) for x in fixed] + [""]
lines.append(f"Open homework items: **{open_n}**")
Path("summary.md").write_text("\n".join(lines) + "\n")

with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as out:
    out.write(f"course={course}\nquiz={quiz_id}\nscore={score}/{total}\n")
