# Knowledge Base Quick Start

## Location

The knowledge base is stored globally at:
```
~/.fast-app/knowledge.db
```

This is separate from application-specific cache data (in `output/`).

## Commands

```bash
# View statistics
fast-app profile show

# Export to JSON
fast-app profile dump

# Import from JSON
fast-app profile load knowledge_export.json

# Interactive exploration (recommended)
harlequin ~/.fast-app/knowledge.db
```

## How It Works

### During Resume Generation

1. **Initialization** (`fast-app generate`)
   - KB is automatically created at `~/.fast-app/knowledge.db`
   - Existing facts are loaded and stats shown (with `--verbose` or `--debug`)

2. **Q&A Session**
   - Facts extracted from answers
   - Fact types auto-detected (skill/experience/achievement/preference/general)
   - Each fact stored with initial confidence (0.9)

3. **Before Generation**
   - Relevant facts retrieved based on job keywords
   - Low-confidence facts (<0.5) filtered out
   - Facts boost resume content

4. **After Generation**
   - Generation event recorded
   - Linked facts tracked for future analysis
   - Summary displayed

### Knowledge Decay

Facts decay over time at different rates:
- Skills: 0.998 decay (~180 day half-life)
- Experience: 0.996 (~120 day half-life)
- Achievements: 0.997 (~150 day half-life)
- Preferences: 0.990 (~70 day half-life)
- General: 0.995 (~140 day half-life)

### Debugging

Use `--verbose` or `--debug` flags:

```bash
fast-app generate <url> --verbose
```

Output includes:
```
📚 Knowledge base: /Users/you/.fast-app/knowledge.db
   ✓ Knowledge base: 15 facts
      By type: {'skill': 5, 'experience': 6, ...}
      By source: {'qa': 13, 'profile': 2}

📚 Extracting facts from Q&A...
  ✅ Adding fact (skill): Q: What programming languages...
  📊 KB stats: 16 facts

🔍 Searching knowledge base for relevant facts...
  ✅ skill: I know Python... (conf: 95%, rel: 30%)
  ✅ experience: I worked at Google... (conf: 90%, rel: 25%)
  📊 Found 2 relevant facts for this job

📝 Recording generation: Senior Developer at TechCorp
  ✅ Linked 2 facts to generation

📚 Knowledge Base Summary:
   Total facts: 16
   Health score: 92%
   Generations: 1 (0 successful)
   Location: /Users/you/.fast-app/knowledge.db
```

## Exploring with Harlequin

Install Harlequin:
```bash
pip install harlequin
```

Explore your knowledge base:
```bash
harlequin ~/.fast-app/knowledge.db
```

Sample queries:
```sql
-- All skills with high confidence
SELECT * FROM facts 
WHERE type = 'skill' 
AND confidence > 0.8 
ORDER BY confidence DESC;

-- Facts needing refresh
SELECT * FROM facts 
WHERE datetime(last_confirmed) < datetime('now', '-90 days');

-- Recent generations
SELECT * FROM generations 
ORDER BY created_at DESC 
LIMIT 10;

-- Most used facts
SELECT f.text, f.type, COUNT(*) as usage_count
FROM facts f
JOIN fact_usage fu ON f.id = fu.fact_id
GROUP BY f.id
ORDER BY usage_count DESC;
```