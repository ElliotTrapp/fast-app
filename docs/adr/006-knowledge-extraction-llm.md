# ADR-006: Knowledge Extraction via LLM Distillation

## Context

When a user answers interview questions like:

> "Well, I've been coding for about 5 years, mostly in Python, and I led a small team at my last company."

This raw answer contains multiple atomic facts:
1. "5 years of coding experience"
2. "Primary language is Python"
3. "Has team leadership experience"

Storing the raw answer in the vector database would be inefficient because:
- It's verbose (embedding a paragraph vs. a sentence)
- It conflates multiple topics (retrieval may match on one fact but return the whole paragraph)
- It's informal and may not match query terms ("coding" vs. "programming")

We need a **distillation step** that extracts discrete, atomic facts from raw Q&A pairs before embedding.

## Decision

Use an LLM (via LangChain) to extract facts from Q&A pairs. The LLM receives the question, answer, and optionally the user's profile and job context, and outputs a structured list of `ExtractedFact` objects.

### Data model

```python
# models/knowledge.py

class ExtractedFact(BaseModel):
    """A single atomic fact extracted from a Q&A pair."""
    content: str                    # The fact itself: "5 years Python experience"
    category: str                   # Category: "skill", "experience", "education", etc.
    confidence: float               # Confidence score: 0.0 to 1.0
    source_question: str            # Original question that elicited this fact
    source_answer: str             # Original answer text
    
class FactExtractionResult(BaseModel):
    """Result of fact extraction from Q&A pairs."""
    facts: list[ExtractedFact]
    summary: str                   # Brief summary of what was learned
```

### Extraction flow

```
Q&A pairs (questions + answers)
    │
    ▼
┌──────────────────────────────────────┐
│  FactExtractor (LangChain chain)     │
│                                      │
│  Input: questions, answers,          │
│         profile (optional),          │
│         job_data (optional)           │
│                                      │
│  Prompt → LLM → PydanticOutputParser │
│  Output: FactExtractionResult         │
└──────────────────────────────────────┘
    │
    ▼
List[ExtractedFact]
    │
    ▼
┌──────────────────────────────────────┐
│  KnowledgeService (ChromaDB)          │
│                                      │
│  For each fact:                       │
│    1. Embed the fact content          │
│    2. Store with metadata             │
│       (category, confidence, source,  │
│        user_id, job_url)              │
└──────────────────────────────────────┘
```

### Extraction modes

The system supports two modes:

1. **Auto-extract** (default): Facts are extracted and stored automatically after each Q&A session. No user intervention required.

2. **Review mode** (`--review-facts` flag): Facts are extracted but flagged for user review before storage. The user can accept, reject, or edit each fact. This provides control over what enters the knowledge base.

```python
# CLI usage
fast-app generate <url>                      # Auto-extract (default)
fast-app generate <url> --review-facts       # Review mode

# Webapp usage
# Settings: "Auto-extract facts" (on/off toggle)
# Review UI: List of extracted facts with accept/reject/edit buttons
```

### Prompt design

The fact extraction prompt is carefully designed to produce structured, atomic output:

```python
# prompts/fact_extraction.py

FACT_EXTRACTION_PROMPT = """You are a knowledge extraction specialist. Your task is to distill 
discrete, atomic facts from interview Q&A pairs.

## Rules
1. Each fact must be a single, self-contained statement
2. Each fact must be specific (not vague like "has experience")
3. Categorize each fact into one of: skill, experience, education, certification, 
   preference, personality, goal
4. Assign a confidence score (0.0-1.0) based on how clearly the fact was stated
5. Do not infer facts that aren't supported by the answer
6. Do not duplicate facts already in the known profile

## Known Profile
{profile_data}

## Job Context
{job_data}

## Q&A Pairs
{qa_pairs}

## Output Format
Return a JSON object with:
- "facts": array of {content, category, confidence, source_question, source_answer}
- "summary": brief summary of what was learned (1-2 sentences)
"""
```

### LangChain chain implementation

```python
# services/fact_extractor.py

class FactExtractor:
    """Extracts atomic facts from Q&A pairs using LLM distillation."""
    
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service
        self.chain = (
            get_fact_extraction_template()
            | self.llm._llm
            | PydanticOutputParser(pydantic_object=FactExtractionResult)
        )
    
    def extract_facts(
        self,
        questions: list[str],
        answers: list[str],
        profile_data: dict | None = None,
        job_data: dict | None = None,
    ) -> FactExtractionResult:
        """Extract facts from Q&A pairs.
        
        Args:
            questions: List of question strings
            answers: List of answer strings (same length as questions)
            profile_data: Optional user profile for deduplication
            job_data: Optional job context for relevance filtering
            
        Returns:
            FactExtractionResult with extracted facts and summary
        """
        qa_pairs = "\n".join(
            f"Q: {q}\nA: {a}" for q, a in zip(questions, answers)
        )
        
        result = self.chain.invoke({
            "qa_pairs": qa_pairs,
            "profile_data": json.dumps(profile_data or {}),
            "job_data": json.dumps(job_data or {}),
        })
        
        return result
```

### Integration into existing pipeline

```python
# In background_tasks.py or CLI pipeline

# After Q&A is complete:
if config.llm.provider and knowledge_service:
    # Auto-extract mode (default)
    facts = fact_extractor.extract_facts(questions, answers, profile, job_data)
    knowledge_service.store_facts(user_id=user_id, facts=facts.facts)
    logger.info(f"Extracted and stored {len(facts.facts)} facts")

# In review mode:
if review_mode:
    facts = fact_extractor.extract_facts(questions, answers, profile, job_data)
    for fact in facts.facts:
        # Present to user for review
        accepted = click.confirm(f"  Fact: {fact.content} ({fact.category}, {fact.confidence:.0%})")
        if accepted:
            knowledge_service.store_facts(user_id=user_id, facts=[fact])
```

## Consequences

### Positive

- **Precise retrieval**: Atomic facts match queries better than verbose Q&A excerpts
- **Deduplication**: Facts can be compared to existing knowledge to avoid storing duplicates
- **User control**: Review mode lets users verify what enters their knowledge base
- **Category filtering**: Metadata allows querying by category ("show me all skills")
- **Confidence scores**: Low-confidence facts can be flagged for review or excluded from retrieval

### Negative

- **LLM cost**: Each Q&A session triggers an additional LLM call for fact extraction. At ~500 tokens per extraction, this is modest (~1 cent per session with typical models).
- **Extraction quality**: The LLM might miss facts, hallucinate facts, or extract improperly. Review mode mitigates this. The prompt is designed to minimize these issues.
- **Latency**: An extra LLM call adds ~2-5 seconds. Acceptable since it happens after Q&A, not blocking the user.
- **Complexity**: Another LangChain chain to maintain and test. Mitigated by clear separation of concerns (FactExtractor is independent).

### Why LLM distillation instead of alternatives?

| Approach | Why not |
|----------|---------|
| **Store raw answers** | Verbose, conflates topics, poor retrieval |
| **NLP sentence splitting** | No semantic understanding; "5 years in Python" stays as-is without categorization |
| **Rule-based extraction** | Brittle, doesn't generalize across answer formats |
| **Manual fact entry** | Defeats the purpose of automation; 80% functionality goal |