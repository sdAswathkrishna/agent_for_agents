# 3-Minute Demo Video Script
## GitAgent Hackathon — BuilderAI

**Format:** Screen recording + voice-over
**Total runtime:** 3:00
**Screen layout:** Terminal (left) + Browser (right)
**Tone:** Direct, confident, unhurried — like a developer showing a colleague something that genuinely works

---

## [0:00 – 0:18] — The Hook + Spec Check

**Show:** Terminal, `cd agent-for-agents-lyzr`, cursor blinking.

**Say:**
> "I built an agent that builds other agents.
> You describe what you want — it asks the right questions, draws the architecture,
> and hands you production-ready code, packaged as a GitAgent-compliant spec.
> Let me show you."

**Show:** Type and run:
```bash
gitagent validate
gitagent info
```

**Say:**
> "The spec validates clean — zero errors, zero warnings.
> Two skills, three tools, running on gpt-4o."

---

## [0:18 – 0:35] — Start the Server, Open the UI

**Show:** Type in terminal:
```bash
uvicorn main_api:app --reload --port 8000
```

**Say:**
> "I'll start the server and open the BuilderAI interface."

**Show:** Server starts. Switch to browser, navigate to `http://localhost:8000/ui/`.
BuilderAI loads — sidebar on the left, clean dark chat panel, Builder panel on the right.

---

## [0:35 – 1:20] — Build an Agent Through the UI

**Show:** Click **New** in the sidebar. Type "Customer Support Agent". Press Enter.

**Say:**
> "New project. I'll describe what I need."

**Show:** Type in the chat:
> "I want a customer support agent that searches a knowledge base, escalates unresolved issues to a human, and updates ticket status in Zendesk."

**Show:** Agent responds with the first question. Continue answering naturally — 3 to 4 exchanges. The stage label at the top of the chat advances: Requirements → Tech Stack → Details → Architecture.

**Say:**
> "The OrchestratorAgent walks through a six-stage requirements conversation.
> It's asking the right questions in the right order.
> Once the architecture is confirmed, it signals it's ready."

---

## [1:20 – 1:45] — Generate the Agent

**Show:** The inline **Generate Agent** button appears in the chat after the architecture message. Click it.

**Say:**
> "One click. The CodeGeneratorAgent takes over."

**Show:** The right panel animates through the build steps — Initialising, Writing Tools, Assembling Agent, Packaging Files — each step ticking green in sequence.

**Show:** Generation completes. Panel switches automatically to the Files tab.

---

## [1:45 – 2:05] — Review Files, Download ZIP

**Show:** Click through the file tree — `agent.py`, `tools/search_knowledge_base.py`, `agent.yaml`.

**Say:**
> "Real code. Not scaffolding, not stubs.
> The tools make actual API calls. The agent.py has a working chat loop.
> The GitAgent spec files are here too — agent.yaml, SOUL.md, RULES.md."

**Show:** Click the **Download ZIP** button in the top-right topbar (it's now active). ZIP downloads.

---

## [2:05 – 2:25] — Open in Cursor

**Show:** Open Cursor. Drag the unzipped folder in. Navigate to `agent.py`, then `tools/escalate_to_human.py`.

**Say:**
> "I can open this directly in Cursor and run it.
> Real httpx calls, environment variable credentials, proper error handling.
> This is production code, not a template."

---

## [2:25 – 2:50] — Validate and Run the Generated Agent

**Show:** In terminal, `cd` into the unzipped agent folder. Run:
```bash
gitagent validate
```

**Show:** All green — 0 errors, 0 warnings.

**Say:**
> "The generated spec passes gitagent validate out of the box.
> The CodeGeneratorAgent is producing GitAgent-compliant output — not just Python."

**Show:** Run:
```bash
source .env
gitagent run -a lyzr -p "hi"
```

**Show:** Agent responds.

**Say:**
> "And it runs. One command. From the generated spec, against the Lyzr adapter."

---

## [2:50 – 3:00] — Close

**Show:** Terminal cursor blinking.

**Say:**
> "GitAgent solves the right problem — agents should be versioned, portable, and owned by their builders.
> This is what that looks like end to end."

**Show:** Fade out.

---

## Recording Checklist

- [ ] Font size 16+ in terminal for readability
- [ ] Clear terminal between sections (`clear`)
- [ ] `source .env` before any `gitagent run` command
- [ ] Have the unzipped agent folder ready in Cursor before recording (run generation once beforehand)
- [ ] Have at least one existing project in the BuilderAI sidebar so the UI doesn't look empty at start
- [ ] Silence notifications (Do Not Disturb on)
- [ ] Record at 1920×1080

---

## Timing Reference

| Section | Start | End | Duration |
|---------|-------|-----|----------|
| Hook + validate + info | 0:00 | 0:18 | 18s |
| Start server + open UI | 0:18 | 0:35 | 17s |
| Chat and build | 0:35 | 1:20 | 45s |
| Generate agent | 1:20 | 1:45 | 25s |
| Review files + download | 1:45 | 2:05 | 20s |
| Open in Cursor | 2:05 | 2:25 | 20s |
| Validate + run generated | 2:25 | 2:50 | 25s |
| Close | 2:50 | 3:00 | 10s |
| **Total** | | | **3:00** |
