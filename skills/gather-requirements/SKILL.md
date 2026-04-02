---
name: gather-requirements
description: "Guide users through a structured 6-state conversation to capture complete AI agent requirements"
license: MIT
allowed-tools: "generate-diagram"
metadata:
  category: conversation
  states: "6"
  output-model: OrchestratorOutput
---

## Overview

This skill drives the OrchestratorAgent through a deliberate 6-state requirement
gathering conversation. Every state has a clear goal and transition condition.
The agent must not move to the next state until the current state's goal is met.

## State Sequence

```
intro → requirements → tech → details → review → architecture → [complete]
```

## State Definitions

### State 1: intro
**Goal**: Understand the agent's core purpose in plain terms.
**Capture**: `problem`, `target_users`
**Transition trigger**: User has described what the agent should do and who uses it.

### State 2: requirements
**Goal**: Identify tools, triggers, and integrations.
**Capture**: `tools[]`, `triggers[]`, `integrations[]`
**Transition trigger**: At least one tool and one trigger identified.

### State 3: tech
**Goal**: Confirm Lyzr ADK as the framework; agree on LLM provider.
**Capture**: `tech_stack = "lyzr-adk"`, LLM provider preference
**Transition trigger**: User has confirmed (or accepted default gpt-4o).

### State 4: details
**Goal**: Gather specifics — multi-user, storage, RAG, guardrails.
**Capture**: `multi_user`, `aws_services`, knowledge base requirements
**Transition trigger**: All detail questions answered (or user says "skip").

### State 5: review
**Goal**: Present full requirements summary and get explicit confirmation.
**Capture**: Nothing new — this is a confirmation gate.
**Transition trigger**: User says "yes", "looks good", "correct", or equivalent.

### State 6: architecture
**Goal**: Generate diagram and mark conversation complete.
**Steps**:
1. Call `generate_diagram(description=<full architecture description>)`
2. Report result to user
3. Set `is_complete = True`

## Structured Output

Every turn returns `OrchestratorOutput`:
```json
{
  "message": "The conversational response shown to the user",
  "conversation_state": "intro|requirements|tech|details|review|architecture|complete",
  "extracted_requirements": { /* Requirements object */ },
  "is_complete": false,
  "diagram_path": null
}
```

## Conversation Principles

- Ask max 3 questions per message
- Use bullet points for option lists
- Reference what the user said in follow-ups to show active listening
- If the user gives a vague answer, ask one clarifying question before moving on
