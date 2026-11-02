# IT Support Toolkit

A small Python command-line tool that mimics what a first-line (Tier 1) IT support person does: diagnose a problem, log a ticket, and write a how-to article.

> **Honest note:** I'm learning Python and built this with a lot of AI assistance. I work through each piece until I can explain it, and I note what I learned each day below.

## Setup

```bash
git clone <your-repo-url>
cd it-support-toolkit
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python toolkit.py hello
```

## Commands

| Command | What it does | Status |
|---|---|---|
| `python toolkit.py hello` | Checks the tool runs | Day 1 |
| `python toolkit.py diagnose` | Checks internet by IP, then DNS, and suggests a fix | Day 1 |
| `python toolkit.py ticket add/list` | Log and list tickets with priority (SQLite) | Day 4-5 |
| `python toolkit.py kb list/show` | Read how-to articles from `kb/` | Day 6 |

## 7-day plan

1. **Day 1** - Repo, `hello`, `diagnose`. Learn: IP vs DNS.
2. **Day 2** - Add a ping check and a DNS lookup check. Learn: ping, traceroute.
3. **Day 3** - Add a system check (disk space, memory) with `psutil`. Learn: basic Windows troubleshooting.
4. **Day 4** - `ticket add`: save tickets to SQLite. Learn: ticket fields.
5. **Day 5** - Priority from impact x urgency, plus `ticket list`. Learn: priority and escalation.
6. **Day 6** - `kb` command and 3 how-to articles in `kb/`.
7. **Day 7** - Tidy README, add screenshots, push to GitHub.

## What I learned

- Day 1: _write 2-3 sentences in your own words._
