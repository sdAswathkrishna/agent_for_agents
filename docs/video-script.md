# 3-Minute Demo Video Script
## GitAgent Hackathon — Agent-for-Agents

**Format:** Screen recording + voice-over
**Total runtime:** 3:00
**Screen layout:** Terminal (left) + Browser (right) when needed
**Tone:** Direct, confident, unhurried — like a developer showing a colleague something that genuinely works

---

## [0:00 – 0:18] — The Hook

**Show:** Terminal, `cd agent-for-agents-lyzr`, cursor blinking.

**Say:**
> "I built an agent that builds other agents.
> You describe what you want — it asks the right questions, draws the architecture,
> and hands you production-ready code.
> Everything is packaged with the GitAgent standard — which means it runs from a GitHub URL
> with a single command. Let me show you."

---

## [0:18 – 0:35] — GitAgent Validation

**Show:** Type and run:
```bash
gitagent validate
```

**Say:**
> "First — the GitAgent spec check. This validates the agent.yaml, SOUL.md, skills, and tool definitions
> against the open standard."

**Show:** Output appears line by line — all green checkmarks, `Validation passed (0 warnings)`.

**Say:**
> "Zero errors. Zero warnings."

**Show:** Then run:
```bash
gitagent info
```

**Say:**
> "The agent has two skills — gather requirements and generate code — three tools, and it runs on gpt-4o."

---

## [0:35 – 1:20] — Run from GitHub (The Portability Moment)

**Show:** Type:
```bash
gitagent run -r https://github.com/sdAswathkrishna/agent_for_agents \
  -a lyzr \
  -p "I want to build an invoice processing agent for a finance team"
```

**Say:**
> "Now the key part. I'm not running from a local directory.
> I'm pointing GitAgent at my GitHub repo — it clones it, reads the spec, connects to Lyzr,
> and starts the conversation. This is what #OwnYourAgents actually means:
> the agent lives in Git. Anyone can run it, from anywhere, against any adapter."

**Show:** Output appears:
```
Resolving repository
URL: https://github.com/sdAswathkrishna/agent_for_agents
Running agent: agent-for-agents v1.0.0
Using existing Lyzr agent: 69cd5f3e51239b22df1cae8e
[STATE 1/6: intro]
Great! Let's start by understanding...
```

**Say:**
> "State one of six. The OrchestratorAgent is live."

---

## [1:20 – 1:55] — The Generated Output

**Show:** Switch to the artifacts folder:
```bash
ls artifacts/a73b5863.../
cat artifacts/a73b5863.../agent.py
```

**Say:**
> "This is what the system produces after a completed conversation.
> A full Lyzr ADK project — agent.py, three tool files, requirements.txt, README, .env.example.
> Not scaffolding. Not pseudocode. This runs."

**Show:** Scroll through `agent.py` — `from lyzr import Studio`, `studio.create_agent(...)`,
`agent.add_tool(order_lookup)`, `agent.run(prompt, session_id=...)`.

**Say:**
> "It imports the Lyzr SDK, creates the agent with the right config, registers the tools,
> and wires up session memory. The pattern is correct because the code generator
> was trained on real Lyzr ADK patterns — not documentation."

---

## [1:55 – 2:20] — Export to Any Framework

**Show:** Run:
```bash
gitagent export --format claude-code | head -20
gitagent export --format crewai | head -15
```

**Say:**
> "The same agent.yaml exports to Claude Code, OpenAI, CrewAI, OpenClaw.
> One definition. Every adapter.
> This is the difference between an agent and a locked-in prompt buried in someone's platform."

---

## [2:20 – 2:40] — NexaFlow: Testing Lyzr's RAG

**Show:** Switch to `chat_agent_lyzr` directory, run:
```bash
gitagent run -d . -a lyzr -p "How do I cancel my NexaFlow subscription?"
```

**Say:**
> "I also built a production RAG chatbot — NexaFlow — specifically to test Lyzr's
> native Knowledge Base feature and document how it compares to building the same
> pipeline on AWS. The short version: Lyzr's managed KB reduced a two-week Lambda
> build to twenty minutes and sixty-three percent less code.
> The full comparison — including twelve friction points I hit and fixed — is in the repo."

**Show:** Answer streams back — `[CONFIDENCE: 0.87] [ANSWER_TYPE: AI_GOT_THE_ANSWER]`

---

## [2:40 – 3:00] — Close

**Show:** Browser — open `https://github.com/sdAswathkrishna/agent_for_agents`, scroll README briefly.

**Say:**
> "Both agents pass gitagent validate. Both are live on Lyzr Studio.
> The agent-for-agents repo is at github.com/sdAswathkrishna/agent_for_agents.
>
> GitAgent solves the right problem — agents should be owned by their builders,
> versioned like code, and portable across frameworks.
> I wanted to see exactly how far that idea holds in practice.
> The answer is: pretty far — with a few sharp edges worth documenting."

**Show:** Terminal — cursor. Fade out.

---

## Recording Checklist

- [ ] Font size 16+ in terminal for readability
- [ ] Clear terminal between sections (`clear`)
- [ ] `source .env` before any `gitagent run` command
- [ ] Have `artifacts/a73b5863.../` populated before recording (run generation once beforehand)
- [ ] Browser tab pre-loaded at `https://github.com/sdAswathkrishna/agent_for_agents`
- [ ] Silence notifications (Do Not Disturb on)
- [ ] Record at 1920×1080

---

## Timing Reference

| Section | Start | End | Duration |
|---------|-------|-----|----------|
| Hook | 0:00 | 0:18 | 18s |
| GitAgent validate + info | 0:18 | 0:35 | 17s |
| Run from GitHub | 0:35 | 1:20 | 45s |
| Generated output | 1:20 | 1:55 | 35s |
| Export formats | 1:55 | 2:20 | 25s |
| NexaFlow mention | 2:20 | 2:40 | 20s |
| Close | 2:40 | 3:00 | 20s |
| **Total** | | | **3:00** |
