---
name: interview
description: Conduct an in-depth interview with the user about a spec - either from a file or described inline. Covers technical implementation, UI/UX, concerns, tradeoffs, edge cases, and more. Use when the user says /interview.
argument-hint: [path-to-spec.md or inline spec description]
allowed-tools: Read, AskUserQuestion, Edit, Write, Glob
---

## Instructions

1. **Get the spec**: Determine the source of the spec:
   - If `$ARGUMENTS` is a file path (ends in `.md`, contains `/`, or points to an existing file), read that file.
   - If `$ARGUMENTS` is provided but is NOT a file path, treat the argument text itself as the spec description.
   - If no arguments were provided, ask the user using AskUserQuestion: "Would you like to point me to a spec file, or describe your idea right here?" Then proceed based on their response.

2. **Analyze deeply**: Identify every area that is underspecified, ambiguous, or has implicit assumptions. Think about:
   - Technical implementation details that are glossed over
   - UI/UX flows that aren't fully described
   - Edge cases and error states
   - Performance and scaling implications
   - Security considerations
   - Data model questions
   - Integration points and dependencies
   - Migration and backwards compatibility
   - Tradeoffs between competing approaches
   - User experience subtleties
   - Accessibility concerns
   - Monitoring and observability

3. **Interview the user**: Ask questions one at a time using AskUserQuestion. Rules:
   - Do NOT ask obvious questions whose answers are already in the spec
   - Do NOT ask generic questions - every question must be specific to THIS spec
   - Go deep - ask follow-up questions when answers reveal new ambiguity
   - Challenge assumptions - ask "why" and "what if" questions
   - Ask about tradeoffs: "You chose X, but Y would give you Z - was that considered?"
   - Cover the non-obvious: failure modes, edge cases, what happens at scale
   - Keep going until you've thoroughly covered every aspect of the spec

4. **Write the results**: Once the interview is complete:
   - If the spec came from a file, update that file with all new details, decisions, and clarifications. Preserve the original structure but enrich it.
   - If the spec was provided inline (no file), ask the user where they'd like the final spec written, then create a well-structured spec file incorporating everything from the interview.
   - Add new sections as needed.