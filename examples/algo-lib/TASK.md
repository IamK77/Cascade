# Task: Build a Python Algorithm Library

In this directory (`examples/algo-lib/`), build a Python package called `algopy` — a comprehensive algorithm library covering the following categories:

## Requirements

### Sorting Algorithms
Bubble sort, merge sort, quick sort, heap sort, radix sort. All should work on `list[int]` and return a new sorted list.

### Searching Algorithms
Binary search, interpolation search, jump search, exponential search. All take a sorted list and a target, return the index or -1.

### Graph Algorithms
BFS, DFS, Dijkstra's shortest path, topological sort, Kruskal's MST. Use adjacency list representation (`dict[str, list[tuple[str, int]]]`).

### String Algorithms
KMP pattern matching, Rabin-Karp, Levenshtein distance, longest common subsequence, trie implementation with insert/search/prefix.

### Math Algorithms
GCD (Euclidean), prime sieve (Eratosthenes), fast exponentiation, matrix multiplication, simple FFT.

### Dynamic Programming
0/1 knapsack, longest increasing subsequence, edit distance, coin change (min coins), longest common subsequence (tabulated).

### Tree Algorithms
Binary search tree (insert/search/delete), AVL rotation helpers, serialize/deserialize binary tree, lowest common ancestor, tree diameter.

### Compression
Huffman coding (encode/decode), run-length encoding, LZ77 basic implementation.

### Cryptography
Caesar cipher, Vigenère cipher, simple SHA-256 (educational, not production), base64 encode/decode.

### Geometry
Convex hull (Graham scan), line segment intersection, point-in-polygon, closest pair of points.

## Package Structure

```
algopy/
  __init__.py
  sorting.py
  searching.py
  graph.py
  strings.py
  math_algo.py
  dp.py
  trees.py
  compression.py
  crypto.py
  geometry.py
tests/
  test_sorting.py
  test_searching.py
  ... (one test file per module)
```

## Constraints

- Pure Python, no external dependencies
- Every function must have type hints
- Every module must have at least 10 test cases
- All tests must pass with `python -m pytest tests/ -v`

## How to Work

Use `/cascade` to coordinate this work. Maximize parallelism — the 10 algorithm modules are completely independent of each other.
