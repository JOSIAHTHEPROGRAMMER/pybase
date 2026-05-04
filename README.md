# PyBase



![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)
![Tests](https://img.shields.io/badge/Tests-67%20passing-brightgreen?style=flat)
![GUI](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=flat&logo=qt&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-Binary%20%2B%20JSON-orange?style=flat)



PyBase is a minimal relational database engine built from scratch in Python. It implements real database internals: custom binary storage, B-Tree indexing, schema persistence, a full constraint system, transactions with savepoints, and a complete query system, without any external libraries except PyQt6 and matplotlib for the GUI.

## Preview

<img width="1918" height="1012" alt="PyBase GUI" src="https://github.com/user-attachments/assets/7e0a8dfa-d84a-4d62-a828-9ac1ff241972" />

## Features

**Core Engine**

Full CRUD with `CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `DROP TABLE`, and `DROP DATABASE`. SQL-like syntax with case-insensitive keywords and all column names normalised to lowercase. Rows are stored in binary `.db` files and schemas in `.schema` JSON files. B-Tree indexing via `CREATE INDEX` gives O(log n) equality lookups, auto-maintained on insert, update, and delete. Multi-statement scripts separated by semicolons are supported.

**Constraints**

`PRIMARY KEY` enforces UNIQUE + NOT NULL on single or composite columns. `UNIQUE`, `NOT NULL`, `DEFAULT`, and `CHECK` are all enforced on insert and update. `AUTO_INCREMENT` persists its counter to the schema so values are never reused after a restart. Foreign keys use `REFERENCES` syntax and are enforced on insert, update, and two-phase commit. `ON DELETE CASCADE` and `ON UPDATE CASCADE` are both supported. Exact duplicate rows are always rejected.

**Query System**

Column projection, `SELECT DISTINCT`, column and table aliases, `ORDER BY` with `ASC`/`DESC`, `LIMIT`, `GROUP BY` with `HAVING`, and aggregates (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`). Set operations include `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT`. Subqueries work in `WHERE` with `IN`, `EXISTS`, `ANY`, and `ALL`. WHERE clauses support comparisons (`=`, `!=`, `<>`, `>`, `>=`, `<`, `<=`), logical operators (`AND`, `OR`, `NOT`), `BETWEEN`, `IN`, `LIKE` with `%` and `_` wildcards, `IS NULL` / `IS NOT NULL`, arithmetic expressions, and bitwise operators (`&`, `|`, `^`, `<<`, `>>`).

**Transactions**

`BEGIN`, `COMMIT`, and `ROLLBACK` are all supported. PyBase uses a two-phase commit model that validates every operation before applying any, giving you true atomicity. FK constraints are validated at commit time and a failed commit auto-cancels the transaction. `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, and `RELEASE SAVEPOINT` let you create named restore points inside a transaction. Nested transactions are blocked.

**Desktop GUI**

SQL editor with syntax highlighting, `Ctrl+Enter` to run, and `Ctrl+/` to toggle line comments. You can highlight a statement and run just that. Multi-statement scripts strip comments automatically. Query history is persisted to `data/history.json`. Results show in a table with row numbers and column headers. Chart tab supports bar, line, pie, scatter, and histogram via matplotlib. Live ER diagram with crow's foot notation and FK relationship lines. Schema browser shows row counts, column types, and constraint tags (PK, FK, UQ, IDX). A green dot in the status bar shows when a transaction is active. `DROP TABLE` and `DROP DATABASE` both prompt for confirmation. Error and status messages are selectable and copyable. Dark Neon theme with `#0f0f0f` background and `#00e599` accent.

## Architecture

```
pybase/
├── core/
│   ├── database.py         # Database registry, table lifecycle, transaction management
│   ├── table.py            # Table operations, constraint enforcement, query execution
│   └── transaction.py      # Two-phase atomic commit, savepoints, BEGIN/COMMIT/ROLLBACK
├── gui/
│   ├── main.py             # QApplication entry point
│   ├── main_window.py      # MainWindow, assembles all panels
│   ├── panels/
│   │   ├── chart.py        # Bar, line, pie, scatter, histogram charts
│   │   ├── editor.py       # SQL editor, syntax highlighting, history, run button
│   │   ├── er_diagram.py   # Live ER diagram with crow's foot FK notation
│   │   ├── results.py      # Tabbed results panel
│   │   └── schema.py       # Schema browser with row counts and constraint tags
│   └── widgets/
│       ├── font.py         # Monospace font fallback helper
│       ├── highlighter.py  # SQL syntax highlighter
│       ├── history.py      # Query history dropdown with persistence
│       └── status_bar.py   # Transaction status indicator
├── query/
│   └── expression.py       # Full expression evaluator: comparisons, logical, arithmetic, bitwise, subqueries
├── storage/
│   ├── btree.py            # B-Tree and BTreeNode data structures
│   ├── index_manager.py    # Owns and manages B-Tree indexes per table
│   ├── pager.py            # Binary row file read/write
│   ├── schema_manager.py   # JSON schema persistence per table
│   └── serializer.py       # Row serialization to/from fixed-width bytes
├── tests/
│   └── test_pybase.py      # Full test suite
└── cli.py                  # SQL parser, dispatcher, and REPL entry point
```

**Layer Responsibilities**

| Layer | Responsibility |
| --- | --- |
| `cli.py` | Parse SQL strings, dispatch to database, print results |
| `core/database.py` | Own all tables, manage transactions, reload tables on startup |
| `core/table.py` | Validate and execute all row operations, enforce constraints |
| `core/transaction.py` | Two-phase atomic commit, buffer operations, savepoints |
| `query/expression.py` | Evaluate WHERE expressions including subquery types |
| `storage/pager.py` | Append rows to disk, rewrite file after delete/update |
| `storage/serializer.py` | Convert rows to fixed-width binary and back |
| `storage/schema_manager.py` | Write and read per-table `.schema` JSON files |
| `storage/btree.py` | Sorted key-value tree with O(log n) search |
| `storage/index_manager.py` | Create, rebuild, and query B-Tree indexes |
| `gui/` | PyQt6 desktop interface: editor, results, charts, ER diagram |

## Getting Started

**Requirements:** Python 3.10+, PyQt6, matplotlib.

```bash
pip install PyQt6 matplotlib
```

Run the CLI:
```bash
cd pybase
python cli.py
```

Run the GUI:
```bash
cd pybase
python -m gui.main
```

Run the tests:
```bash
cd pybase
pytest tests/test_pybase.py -v -s
```

## Supported SQL Syntax

**DDL**

```sql
CREATE TABLE users (id int PRIMARY KEY, name string);

CREATE TABLE employees (
    id int PRIMARY KEY AUTO_INCREMENT,
    name string NOT NULL,
    salary int DEFAULT 50000 CHECK (salary > 0),
    dept_id int REFERENCES departments(id) ON DELETE CASCADE ON UPDATE CASCADE
);

DROP TABLE users;

CREATE INDEX ON users (id);
```

**DML**

```sql
INSERT INTO users VALUES (1, 'Alice');

SELECT * FROM users;
SELECT DISTINCT dept_id FROM employees;
SELECT name AS employee, salary AS pay FROM employees;

SELECT * FROM employees WHERE id = 1;
SELECT * FROM employees WHERE salary BETWEEN 60000 AND 90000;
SELECT * FROM employees WHERE name LIKE 'A%';
SELECT * FROM employees WHERE dept_id IS NULL;
SELECT * FROM employees WHERE salary + 5000 > 100000;
SELECT * FROM employees WHERE dept_id IN (1, 2, 3);

SELECT dept_id, COUNT(*), AVG(salary) FROM employees GROUP BY dept_id;
SELECT dept_id, COUNT(*) FROM employees GROUP BY dept_id HAVING COUNT(*) > 1;

SELECT name FROM employees WHERE dept_id IN (SELECT id FROM departments WHERE name = 'Engineering');
SELECT name FROM employees WHERE salary > ANY (SELECT salary FROM employees WHERE dept_id = 3);
SELECT name FROM employees WHERE salary > ALL (SELECT salary FROM employees WHERE dept_id = 3);
SELECT id FROM departments WHERE EXISTS (SELECT id FROM employees WHERE dept_id = 1);

SELECT name FROM departments
UNION
SELECT name FROM employees;

SELECT * FROM employees ORDER BY salary DESC LIMIT 5;

UPDATE employees SET salary = 95000 WHERE id = 1;
DELETE FROM employees WHERE id = 1;
```

**Transactions and Savepoints**

```sql
BEGIN;
INSERT INTO users VALUES (3, 'Charlie');
INSERT INTO users VALUES (4, 'Dave');
COMMIT;

BEGIN;
INSERT INTO users VALUES (5, 'Eve');
ROLLBACK;

BEGIN;
INSERT INTO employees VALUES (1, 'Alice', 90000, 1);
SAVEPOINT after_alice;
INSERT INTO employees VALUES (2, 'Bob', 80000, 1);
ROLLBACK TO SAVEPOINT after_alice;
COMMIT;

BEGIN;
INSERT INTO employees VALUES (9, 'Alice Jr', 60000, 1);
INSERT INTO employees VALUES (10, 'Bad FK', 60000, 99);
COMMIT;
```

## Data Types

| Type | Python equivalent | Storage size |
| --- | --- | --- |
| `int` | `int` | 4 bytes signed |
| `bigint` | `int` | 8 bytes signed |
| `float` | `float` | 8 bytes IEEE 754 double |
| `boolean` | `bool` | 1 byte |
| `string` | `str` | 256 bytes fixed width |

## Constraints

| Constraint | Behaviour |
| --- | --- |
| `PRIMARY KEY` | UNIQUE + NOT NULL, single column or composite |
| `COMPOSITE PRIMARY KEY` | Uniqueness enforced across the combination of columns |
| `UNIQUE` | No duplicate values, single column or composite |
| `NOT NULL` | Rejects NULL on insert and update |
| `DEFAULT` | Substituted when value is omitted or NULL |
| `CHECK` | Arbitrary comparison evaluated on insert and update |
| `AUTO_INCREMENT` | Counter persisted to schema, never reused after restart |
| `FOREIGN KEY` | Value must exist in referenced table, enforced on insert, update, and commit |
| `ON DELETE CASCADE` | Child rows deleted automatically when parent is deleted |
| `ON UPDATE CASCADE` | Child FK values updated automatically when parent PK changes |
| Duplicate rows | Exact duplicate rows always rejected |

## Persistence

Each table produces two files in the `data/` directory. The `.db` file holds fixed-width binary row data. The `.schema` file holds JSON with columns, types, constraints, indexes, foreign keys, and the auto increment counter. On startup the database scans `data/` for `.schema` files, reloads all tables automatically, rebuilds B-Tree indexes, and restores all constraint definitions.

## Transactions

PyBase uses a two-phase atomic commit model. `BEGIN` starts buffering `INSERT`, `UPDATE`, and `DELETE` operations. `COMMIT` runs Phase 1 (validate all operations) then Phase 2 (apply all operations). If Phase 1 finds any violation, nothing is applied and the transaction is auto-cancelled. `ROLLBACK` discards the buffer and nothing is written. `SAVEPOINT name` creates a named restore point inside the active transaction. `ROLLBACK TO SAVEPOINT name` undoes back to that point without ending the transaction. `RELEASE SAVEPOINT name` discards a savepoint once it is no longer needed. `SELECT` always reads live committed data, even inside a transaction. `DROP TABLE` and `DROP DATABASE` are blocked inside a transaction. Nested transactions are not supported.

## GUI

```bash
python -m gui.main
```

| Panel | Description |
| --- | --- |
| SQL Editor | Write and run SQL with syntax highlighting and Ctrl+Enter shortcut |
| Query History | Dropdown of previous queries, persisted across sessions |
| Results Table | Tabbed panel showing query results with row numbers |
| Chart Tab | Auto-renders bar, line, pie, scatter, or histogram from SELECT results |
| ER Diagram Tab | Live entity-relationship diagram with crow's foot FK notation |
| Schema Browser | All tables, column types, constraint tags, and live row counts |
| Status Bar | Green indicator when a transaction is active |