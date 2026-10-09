---
name: keaton_name
tier: 1
pattern: 'Keaton'
confidence: 1.0
output: person
description: Identifies Keaton as the primary user
---

---
name: preference_for_python
tier: 1
pattern: '(?:prefer|like|love|want|always use|stick with|use) (?:Python|python)'
confidence: 0.95
output: tech_preference
description: Keaton prefers Python programming language
---

---
name: preference_for_rust
tier: 1
pattern: '(?:prefer|like|love|want|always use|stick with|use) (?:Rust|rust)'
confidence: 0.95
output: tech_preference
description: Keaton prefers Rust programming language
---

---
name: deadline_mention
tier: 1
pattern: '(?:due|deadline|by|before) (?:\w+ )?(?:the )?(?:next )?(?:week|month|Friday|Thursday|Monday|Wednesday|Tuesday|September|October|November|December|January|February|March|April|May|June|July|August)(?: (?:the )?\d{1,2})?'
confidence: 0.9
output: deadline
description: Any stated deadline or due date
examples:
  - due next Friday
  - deadline October 15
  - by December 1
negations:
  - no deadline
  - no due date
  - no fixed deadline
---

---
name: course_code
tier: 2
pattern: '(?:ACCT|CS|ENG|MATH|PHYS|CHEM|BIO|PSY|SOC|HIST|ECON|STAT|BUS|FSAE|ME|ECE)[ ]?\d{3,4}'
confidence: 0.95
output: course
description: University course codes like ACCT 2100, CS 301
examples:
  - ACCT 2100
  - CS 301
  - FSAE 400
---

---
name: location_mention
tier: 2
pattern: '(?:at|in|from|near|to) (?:the )?(?:library|lab|office|studio|room|building|campus|home|work|shop)'
confidence: 0.9
output: location
description: Mentioned physical locations
examples:
  - at the library
  - in the lab
  - from campus
---

---
name: meeting_scheduled
tier: 1
pattern: '(?:meeting|appoint|office hours|chat) (?:with|and)?(?:\w+(?:[\s-]+\w+)*)?'
confidence: 0.85
output: meeting
description: Scheduled meetings or appointments
---

---
name: sleep_duration_mention
tier: 1
pattern: '(?:sleep(?:ed)?|slept|got)?\s*\d+\.?\d*\s*(?:hours?|hrs?|h)'
confidence: 0.95
output: sleep_data
description: Stated sleep duration
examples:
  - slept 6 hours
  - got 7.5 hours of sleep
  - 8 hrs of rest
---

---
name: stress_mention
tier: 1
pattern: '(?:stress|stressed|anxious|anxiety|worried|concerned|overwhelm|burnout|burning out)'
confidence: 0.9
output: stress_indicator
description: Any mention of stress, anxiety, or burnout
---

---
name: goal_statement
tier: 1
pattern: '(?:want to|going to|planning to|aim to|intend to|plan to|goal is|my goal) to (\w+(?:[\s-]+\w+)*)'
confidence: 0.85
output: goal
description: Expressed goals or intentions
negations:
  - no goal
  - no plan
---

---
name: tool_mention
tier: 2
pattern: '(?:tool|library|framework|package|use|using|uses) (?:the )?(?:[a-zA-Z][a-zA-Z0-9_-]+)'
confidence: 0.7
output: tool_reference
description: References to tools, libraries, or frameworks
negations:
  - don't need a tool
  - not using any tool
---

---
name: abbreviation_definition
tier: 3
pattern: '(?:abbreviated as|abbreviated to|short for|aka|also known as|stands for) \w+(?:[\s-]+\w+)*'
confidence: 0.85
output: abbreviation
description: Definition of abbreviations or terms
examples:
  - short for FSAE
  - aka the team
  - stands for CAD
---

---
name: running_reference
tier: 3
pattern: '(?:remember when|back when|that time|last time|that one time) (?:I|we|you) [a-zA-Z\s,.-]+'
confidence: 0.7
output: running_reference
description: References to past conversations or events
---

---
name: food_preference
tier: 3
pattern: '(?:don.t eat|don.t like|dislike|allergic to|avoid|never eat|stop eating) \w+(?:[\s-]+\w+)?'
confidence: 0.85
output: food_restriction
description: Foods Keaton avoids or dislikes
---

---
name: nickname_mention
tier: 3
pattern: '(?:call me|call myself|nickname|go by|I.m called) (\w+)'
confidence: 0.8
output: nickname
description: Self-referenced nicknames or running jokes
---
