---
description: Enterprise Rust, Go, Java, and C# Idiomatic Safety & Concurrency Directives
globs: ["**/*.rs", "**/*.go", "**/*.java", "**/*.cs"]
---

# ⚙️ Enterprise Compiled Languages Cognitive Directives (Rust / Go / Java / C#)

## 1. Rust Directives
- **Ownership & Borrowing**: Respect ownership semantics. Avoid gratuitous `.clone()` calls.
- **Panic Prevention**: Never invoke `.unwrap()` or `.expect()` in production code paths. Handle `Result<T, E>` and `Option<T>` explicitly using `?`, `match`, `if let`, or `unwrap_or_else`.
- **Resource Cleanup**: Leverage RAII and the `Drop` trait for deterministic resource release.
- **Concurrency**: Use `tokio` or `crossbeam` channels. Ensure thread safety with `Arc<Mutex<T>>` or `RwLock<T>`.

## 2. Go Directives
- **Explicit Error Propagation**: Always check errors explicitly (`if err != nil`). Never discard errors with `_`.
- **Panic Prohibition**: Never call `panic()` in production code; return an `error` value instead.
- **Mutex Lifecycle**: Always invoke `defer mu.Unlock()` (or `defer mu.RUnlock()`) immediately following `mu.Lock()`.
- **Context Propagation**: Always pass `ctx context.Context` as the first argument in blocking or I/O calls.
- **Goroutine Leak Prevention**: Use `sync.WaitGroup` or cancelable contexts to guarantee termination of all spawned goroutines.

## 3. Java & C# Directives
- **Records & Immutability**: Use modern `record` types and pattern matching.
- **Null Safety**: Enforce explicit nullability annotations (`@NotNull`, `@Nullable`, C# nullable reference types `#nullable enable`).
- **Resource Management**: Use `try-with-resources` (Java) or `using` statements (C#) for deterministic cleanup.
