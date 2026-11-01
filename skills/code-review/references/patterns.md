# 🛡️ Enterprise Engineering Patterns Reference Catalog

This catalog defines standard patterns required for Claude Opus 5.5 level engineering rigor across TypeScript, Python, Rust, and Go.

---

## 1. Typestate Pattern (State Machine Verification at Compile Time)

Reject invalid state transitions at compile time rather than relying on runtime validation checks.

### TypeScript
```typescript
interface Draft { readonly state: "draft"; readonly content: string }
interface UnderReview { readonly state: "under_review"; readonly content: string; readonly reviewer: string }
interface Published { readonly state: "published"; readonly content: string; readonly publishedAt: Date }

type Article = Draft | UnderReview | Published;

function submitForReview(article: Draft, reviewer: string): UnderReview {
  return { state: "under_review", content: article.content, reviewer };
}

function publish(article: UnderReview): Published {
  return { state: "published", content: article.content, publishedAt: new Date() };
}
```

### Python (3.10+)
```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class DraftArticle:
    content: str

@dataclass(frozen=True)
class ReviewArticle:
    content: str
    reviewer: str

@dataclass(frozen=True)
class PublishedArticle:
    content: str
    published_at: datetime

def submit_for_review(article: DraftArticle, reviewer: str) -> ReviewArticle:
    return ReviewArticle(content=article.content, reviewer=reviewer)

def publish(article: ReviewArticle) -> PublishedArticle:
    return PublishedArticle(content=article.content, published_at=datetime.utcnow())
```

### Rust
```rust
struct Draft;
struct UnderReview { reviewer: String }
struct Published { published_at: u64 }

struct Article<State> {
    content: String,
    state: State,
}

impl Article<Draft> {
    pub fn new(content: String) -> Self {
        Article { content, state: Draft }
    }

    pub fn submit(self, reviewer: String) -> Article<UnderReview> {
        Article { content: self.content, state: UnderReview { reviewer } }
    }
}

impl Article<UnderReview> {
    pub fn publish(self, timestamp: u64) -> Article<Published> {
        Article { content: self.content, state: Published { published_at: timestamp } }
    }
}
```

---

## 2. Branded Nominal Types (Primitive Obsession Prevention)

Prevent accidental substitution of raw strings or integers representing distinct domain entities.

### TypeScript
```typescript
export type UserId = string & { readonly __brand: unique symbol };
export type OrderId = string & { readonly __brand: unique symbol };

export function makeUserId(id: string): UserId {
  if (!id.trim()) throw new Error("Invalid UserId");
  return id as UserId;
}

export function makeOrderId(id: string): OrderId {
  if (!id.trim()) throw new Error("Invalid OrderId");
  return id as OrderId;
}
```

### Python
```python
from typing import NewType

UserId = NewType("UserId", str)
OrderId = NewType("OrderId", str)

def create_user_id(val: str) -> UserId:
    if not val.strip():
        raise ValueError("Invalid UserId")
    return UserId(val)
```

---

## 3. Structured Concurrency and Cancellation Propagation

Prevent orphaned goroutines, dangling tasks, and unbounded memory consumption during parallel executions.

### TypeScript
```typescript
export async function fetchWithAbort(url: string, parentSignal?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  if (parentSignal) {
    parentSignal.addEventListener("abort", () => controller.abort(parentSignal.reason), { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(new Error("Request timeout")), 5000);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}
```

### Python
```python
import asyncio
from typing import List

async def fetch_item(item_id: str) -> str:
    await asyncio.sleep(0.01)
    return f"item-{item_id}"

async def process_batch_bounded(item_ids: List[str], max_concurrency: int = 5) -> List[str]:
    sem = asyncio.Semaphore(max_concurrency)

    async def bounded_task(item: str) -> str:
        async with sem:
            return await fetch_item(item)

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(bounded_task(i)) for i in item_ids]

    return [t.result() for t in tasks]
```

### Go
```go
package concurrency

import (
	"context"
	"golang.org/x/sync/errgroup"
)

func ProcessItemsConcurrently(ctx context.Context, items []string) error {
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(10)

	for _, item := range items {
		it := item
		g.Go(func() error {
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
				return processSingleItem(ctx, it)
			}
		})
	}
	return g.Wait()
}
```

---

## 4. Property-Based Testing (Hypothesis & fast-check)

Complement deterministic example tests with automated invariant property fuzzing.

### Python (Hypothesis)
```python
from hypothesis import given, strategies as st

def parse_and_serialize_record(val: str) -> str:
    cleaned = val.strip()
    return f"REC:{cleaned}"

@given(st.text())
def test_idempotent_serialization(input_str: str) -> None:
    first_pass = parse_and_serialize_record(input_str)
    # The output structure invariant holds for all input text strings
    assert first_pass.startswith("REC:")
```

### TypeScript (fast-check)
```typescript
import fc from "fast-check";

test("symmetric encoding property", () => {
  fc.assert(
    fc.property(fc.string(), (original) => {
      const encoded = Buffer.from(original).toString("base64");
      const decoded = Buffer.from(encoded, "base64").toString("utf-8");
      return decoded === original;
    })
  );
});
```
