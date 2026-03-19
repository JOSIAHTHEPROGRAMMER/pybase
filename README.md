# PyBase

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)
![Tests](https://img.shields.io/badge/Tests-67%20passing-brightgreen?style=flat)
![GUI](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=flat&logo=qt&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-Binary%20%2B%20JSON-orange?style=flat)

PyBase is a minimal relational database engine built from scratch in Python. It implements real database internals - custom binary storage, B-Tree indexing, schema persistence, constraints, transactions, and a full operator system - without any external libraries.

---

## Preview

<img width="1918" height="1012" alt="PyBase GUI" src="https://github.com/user-attachments/assets/7e0a8dfa-d84a-4d62-a828-9ac1ff241972" />

## Features

**Core Engine**

- **Full CRUD** - `CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `DROP TABLE`
- **SQL-like syntax** - case-insensitive keywords and column names
- **File-based persistence** - rows stored in binary `.db` files, schema in `.schema` JSON files
- **Schema persistence** - table definitions, constraints, indexes, and foreign keys survive restarts
- **B-Tree indexing** - `CREATE INDEX` for O(log n) equality lookups, auto-maintained on insert, update, delete
- **Multi-statement execution** - run full scripts separated by semicolons

**Constraints**

- `PRIMARY KEY` - UNIQUE + NOT NULL, one per table
- `UNIQUE` - no duplicate values in the column
- `FOREIGN KEY` - `REFERENCES` syntax with FK violation enforcement on insert and update
- Duplicate row prevention

**Query System**

- **Column projection** - `SELECT name, id FROM ...` or `SELECT *`
- **ORDER BY** - `ASC` and `DESC` on any column
- **LIMIT** - cap result set size
- **Rich WHERE clauses** - full operator support:
  - Comparison: `=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`
  - Logical: `AND`, `OR`, `NOT`
  - Range: `BETWEEN low AND high`
  - Set: `IN (val1, val2, ...)`
  - Pattern: `LIKE` with `%` and `_` wildcards
  - Null: `IS NULL`, `IS NOT NULL`
  - Arithmetic in WHERE: `salary + 5000 > 100000`
  - Bitwise: `&`, `|`, `^`, `<<`, `>>`

**Transactions**

- `BEGIN`, `COMMIT`, `ROLLBACK`
- Two-phase commit - validates all operations before applying any (true atomicity)
- FK constraints validated at commit time
- Failed commits auto-cancel the transaction - no manual ROLLBACK needed

**Desktop GUI**

- SQL editor with syntax highlighting and `Ctrl+Enter` to run
- Multi-statement execution with comment stripping
- Query history dropdown - persisted to `data/history.json`
- Results table with row numbers and column headers
- Bar, line, pie, scatter, and histogram chart tab
- Live ER diagram tab with crow's foot notation and FK relationship lines
- Schema browser with table row counts, column types, and constraint tags
- Transaction status indicator
- Dark Neon-inspired theme

---

## Architecture

```
pybase/
├── core/
│   ├── __init__.py
│   ├── database.py         # Database registry, table lifecycle, transaction management
│   ├── table.py            # Table operations, constraint enforcement, query execution
│   └── transaction.py      # Two-phase atomic commit, BEGIN / COMMIT / ROLLBACK
├── gui/
│   ├── __init__.py
│   ├── main.py             # QApplication entry point
│   ├── main_window.py      # MainWindow, assembles all panels
│   ├── panels/
│   │   ├── __init__.py
│   │   ├── chart.py        # Bar, line, pie, scatter, histogram charts
│   │   ├── editor.py       # SQL editor, syntax highlighting, history, run button
│   │   ├── er_diagram.py   # Live ER diagram with crow's foot FK notation
│   │   ├── results.py      # Tabbed results panel
│   │   └── schema.py       # Schema browser with row counts and constraint tags
│   └── widgets/
│       ├── __init__.py
│       ├── font.py         # Monospace font fallback helper
│       ├── highlighter.py  # SQL syntax highlighter
│       ├── history.py      # Query history dropdown with persistence
│       └── status_bar.py   # Transaction status indicator
├── query/
│   ├── __init__.py
│   └── expression.py       # Full expression evaluator, OR, IN, BETWEEN, LIKE, IS NULL, arithmetic, bitwise
├── storage/
│   ├── __init__.py
│   ├── btree.py            # B-Tree and BTreeNode data structures
│   ├── index_manager.py    # Owns and manages B-Tree indexes per table
│   ├── pager.py            # Binary row file read/write
│   ├── schema_manager.py   # JSON schema persistence per table
│   └── serializer.py       # Row serialization to/from bytes
├── tests/
│   └── test_pybase.py      # Full test suite
├── __init__.py
├── .gitignore
├── cli.py                  # SQL parser and REPL entry point
└── README.md
```

### Layer Responsibilities

| Layer                       | Responsibility                                                         |
| --------------------------- | ---------------------------------------------------------------------- |
| `cli.py`                    | Parse SQL strings, dispatch to database, print results                 |
| `core/database.py`          | Own all tables, manage transactions, reload tables on startup          |
| `core/table.py`             | Validate and execute all row operations, enforce constraints           |
| `core/transaction.py`       | Two-phase atomic commit, buffer operations, apply or discard           |
| `query/expression.py`       | Evaluate WHERE expressions including OR, IN, BETWEEN, LIKE, arithmetic |
| `storage/pager.py`          | Append rows to disk, rewrite file after delete/update                  |
| `storage/serializer.py`     | Convert rows to fixed-width binary and back                            |
| `storage/schema_manager.py` | Write and read per-table `.schema` JSON files                          |
| `storage/btree.py`          | Sorted key-value tree with O(log n) search                             |
| `storage/index_manager.py`  | Create, rebuild, and query B-Tree indexes                              |
| `gui/`                      | PyQt6 desktop interface - editor, results, charts, ER diagram          |

---

## Getting Started

### Requirements

- Python 3.10+
- PyQt6 (GUI only)
- matplotlib (charts and ER diagram)

```bash
pip install PyQt6 matplotlib
```

### Run CLI

```bash
cd pybase
python cli.py
```

### Run GUI

```bash
cd pybase
python -m gui.main
```

---

### Preview

<img src="images/pybase.jpg"/>


## Supported SQL Syntax

### DDL

```sql
-- Create a table
CREATE TABLE users (id int PRIMARY KEY, name string);

-- Create a table with foreign key
CREATE TABLE employees (
    id int PRIMARY KEY,
    name string,
    salary int,
    dept_id int REFERENCES departments(id)
);

-- Drop a table
DROP TABLE users;

-- Create a B-Tree index
CREATE INDEX ON users (id);
```

### DML

```sql
-- Insert a row
INSERT INTO users VALUES (1, 'Alice');

-- Select all rows
SELECT * FROM users;

-- Select with column projection
SELECT name FROM users;

-- WHERE with comparison operators
SELECT * FROM users WHERE id = 1;
SELECT * FROM users WHERE id >= 2 AND id != 4;

-- WHERE with OR
SELECT * FROM employees WHERE dept_id = 1 OR dept_id = 2;

-- WHERE with IN
SELECT * FROM employees WHERE dept_id IN (1, 2, 3);

-- WHERE with BETWEEN
SELECT * FROM employees WHERE salary BETWEEN 60000 AND 90000;

-- WHERE with LIKE
SELECT * FROM employees WHERE name LIKE 'A%';
SELECT * FROM employees WHERE name LIKE '_ob';

-- WHERE with IS NULL
SELECT * FROM employees WHERE dept_id IS NULL;
SELECT * FROM employees WHERE dept_id IS NOT NULL;

-- WHERE with arithmetic
SELECT * FROM employees WHERE salary + 5000 > 100000;

-- ORDER BY and LIMIT
SELECT * FROM users ORDER BY name ASC;
SELECT * FROM users ORDER BY id DESC LIMIT 10;

-- Full SELECT
SELECT name, salary FROM employees
WHERE dept_id = 1 AND salary > 80000
ORDER BY salary DESC
LIMIT 5;

-- Update rows
UPDATE users SET name = 'Alice2' WHERE id = 1;

-- Delete rows
DELETE FROM users WHERE id = 1;
```

### Transactions

```sql
-- Commit - both rows land atomically or neither does
BEGIN;
INSERT INTO users VALUES (3, 'Charlie');
INSERT INTO users VALUES (4, 'Dave');
COMMIT;

-- Rollback - nothing is written
BEGIN;
INSERT INTO users VALUES (5, 'Eve');
ROLLBACK;

-- FK violation at commit - transaction auto-cancelled, nothing lands
BEGIN;
INSERT INTO employees VALUES (9, 'Alice Jr', 60000, 1);
INSERT INTO employees VALUES (10, 'Bad FK', 60000, 99);
COMMIT;
```

---

## Data Types

| Type     | Python equivalent | Storage size                     |
| -------- | ----------------- | -------------------------------- |
| `int`    | `int`             | 4 bytes (signed)                 |
| `string` | `str`             | 256 bytes (1 length + 255 chars) |

---

## Constraints

| Constraint     | Behavior                                                                        |
| -------------- | ------------------------------------------------------------------------------- |
| `PRIMARY KEY`  | UNIQUE + NOT NULL, one per table                                                |
| `UNIQUE`       | No duplicate values in the column                                               |
| `REFERENCES`   | FK value must exist in referenced table, enforced on insert, update, and commit |
| Duplicate rows | Exact duplicate rows always rejected                                            |

---

## Persistence

Each table produces two files in the `data/` directory:

| File                | Contents                                                  |
| ------------------- | --------------------------------------------------------- |
| `table_name.db`     | Fixed-width binary row data                               |
| `table_name.schema` | JSON - columns, types, constraints, indexes, foreign keys |

On startup, the database scans `data/` for `.schema` files and reloads all tables automatically, including rebuilding B-Tree indexes and restoring FK definitions.

---

## Transactions

PyBase uses a **two-phase atomic commit** model:

- `BEGIN` starts buffering `INSERT`, `UPDATE`, and `DELETE` operations
- `COMMIT` runs Phase 1 (validate all operations) then Phase 2 (apply all operations)
- If Phase 1 finds any violation, nothing is applied and the transaction is auto-cancelled
- `ROLLBACK` discards the buffer - nothing is written
- `SELECT` always reads live committed data, even inside a transaction
- `DROP TABLE` is blocked inside a transaction
- Nested transactions are not supported
- Failed commits automatically cancel the transaction - no manual ROLLBACK needed

---

## GUI

Run the desktop interface:

```bash
python -m gui.main
```

| Panel          | Description                                                            |
| -------------- | ---------------------------------------------------------------------- |
| SQL Editor     | Write and run SQL with syntax highlighting and Ctrl+Enter shortcut     |
| Query History  | Dropdown of previous queries, persisted across sessions                |
| Results Table  | Tabbed panel showing query results with row numbers                    |
| Chart Tab      | Auto-renders bar, line, pie, scatter, or histogram from SELECT results |
| ER Diagram Tab | Live entity-relationship diagram with crow's foot FK notation          |
| Schema Browser | All tables, column types, constraint tags, and live row counts         |
| Status Bar     | Green indicator when a transaction is active                           |
