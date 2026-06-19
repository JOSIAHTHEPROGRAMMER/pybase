# PyBase

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)
![Coverage](https://img.shields.io/badge/Coverage-50%25%20Required-brightgreen)
[![Build and Test](https://github.com/JOSIAHTHEPROGRAMMER/pybase/actions/workflows/tests.yml/badge.svg)](https://github.com/JOSIAHTHEPROGRAMMER/pybase/actions/workflows/tests.yml)
![GUI](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=flat&logo=qt&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-Binary%20%2B%20JSON-orange?style=flat)

PyBase is a minimal relational database engine built from scratch in Python, without any external libraries except PyQt6 and matplotlib for the GUI. It implements real database internals: custom variable length binary storage with tombstone deletes, B-Tree and hash indexing, schema persistence, a full constraint system, transactions with savepoints, a complete query system with joins and subqueries, DDL operations, and views.

## Preview

<img width="1918" height="1012" alt="PyBase GUI" src="https://github.com/user-attachments/assets/7e0a8dfa-d84a-4d62-a828-9ac1ff241972" />

## Features

**Core Engine**

Full CRUD with `CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `DROP TABLE`, and `DROP DATABASE`. SQL-like syntax with case-insensitive keywords and all column names normalised to lowercase. Rows are stored in binary `.db` files using a variable length tombstone format, and schemas in `.schema` JSON files. B-Tree indexing via `CREATE INDEX` gives O(log n) equality lookups, auto-maintained on insert, update, and delete. Hash indexing via `CREATE HASH INDEX` gives O(1) equality lookups. Composite indexes are supported across multiple columns. Multi-statement scripts separated by semicolons are supported.

**Storage Engine**

Rows are stored with a one byte tombstone flag and a four byte length prefix, allowing variable length data like `TEXT` and `BLOB` to live alongside fixed width types in the same file. Deletes write a tombstone byte in place rather than rewriting the whole file, making deletes a constant time operation regardless of table size. `COMPACT TABLE` reclaims space from tombstoned rows by rewriting the file with only live rows. In memory row offsets are tracked so deletes always target the exact byte position of a row without a full file scan.

**Constraints**

`PRIMARY KEY` enforces UNIQUE + NOT NULL on single or composite columns. `UNIQUE`, `NOT NULL`, `DEFAULT`, and `CHECK` are all enforced on insert and update. `AUTO_INCREMENT` persists its counter to the schema so values are never reused after a restart. Foreign keys use `REFERENCES` syntax and are enforced on insert, update, and two-phase commit. `ON DELETE CASCADE` and `ON UPDATE CASCADE` are both supported. Exact duplicate rows are always rejected.

**Query System**

- Column projection - `SELECT name, id FROM ...` or `SELECT *`
- `SELECT DISTINCT` - removes duplicate rows from the result
- Column aliases - `SELECT salary AS pay FROM emp`
- Table aliases - `FROM employees AS e`
- `ORDER BY` - `ASC` and `DESC` on any column
- `LIMIT` - cap result set size
- `GROUP BY` with `HAVING` - group rows and filter groups
- Aggregate functions - `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`
- Set operations - `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT`
- Subqueries - in `WHERE` with `IN`, `EXISTS`, `ANY`, `ALL`
- B-Tree and hash index used automatically for single equality conditions on indexed columns
- Composite index used automatically when all equality conditions match the indexed columns
- Rich WHERE clauses:
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
- Failed commits auto-cancel the transaction - no manual `ROLLBACK` needed
- `SAVEPOINT name` - create a named restore point inside a transaction
- `ROLLBACK TO SAVEPOINT name` - undo back to a savepoint without ending the transaction
- `RELEASE SAVEPOINT name` - discard a savepoint
- Nested transactions blocked

**Desktop GUI**

- SQL editor with syntax highlighting and `Ctrl+Enter` to run
- `Ctrl+/` to toggle line comments on selected lines
- Run selected text only - highlight a statement and run just that
- Multi-statement execution with comment stripping
- Query history dropdown - persisted to `data/history.json`
- Results table with row numbers and column headers
- Bar, line, pie, scatter, and histogram chart tab via matplotlib
- Live ER diagram tab with crow's foot notation and FK relationship lines
- Schema browser with table row counts, column types, and constraint tags (PK, FK, UQ, IDX)
- Transaction status indicator - green dot when a transaction is active
- `DROP TABLE` and `DROP DATABASE` confirmation dialogs
- Error and status messages are selectable and copyable
- Dark Neon theme - `#0f0f0f` background, `#00e599` accent

---

## Architecture

```
pybase/
├── core/
│   ├── database.py         # Database registry, table lifecycle, views, transaction management
│   ├── table.py            # Table operations, constraint enforcement, query execution, DDL methods
│   └── transaction.py      # Two-phase atomic commit, savepoints, BEGIN/COMMIT/ROLLBACK
├── gui/
│   ├── main.py             # QApplication entry point
│   ├── main_window.py      # MainWindow, assembles all panels
│   ├── panels/
│   │   ├── chart.py        # Bar, line, pie, scatter, histogram charts with NULL handling
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
│   ├── expression.py       # Full expression evaluator - comparisons, logical, arithmetic, bitwise, subqueries
│   ├── planner.py          # Join planning for INNER, LEFT, RIGHT, FULL OUTER, CROSS, SELF joins
│   ├── executor.py         # Executes the join plan and produces result rows
│   └── utils.py            # Shared query helpers, aggregate detection
├── storage/
│   ├── btree.py            # B-Tree and BTreeNode data structures
│   ├── hash_index.py       # Hash index for O(1) equality lookups
│   ├── index_manager.py    # Owns and manages B-Tree, hash, and composite indexes per table
│   ├── pager.py            # Variable length row file read/write with tombstone deletes and compaction
│   ├── schema_manager.py   # JSON schema persistence per table
│   └── serializer.py       # Row serialization to/from variable length binary
├── tests/
│   ├── phase_1_test.py     # Comprehensive Phase 1 test suite (64 tests)
│   └── phase_2_test.py     # Phase 2 test suite - tombstone deletes, TEXT/BLOB/JSON/XML, compaction
└── cli.py                  # SQL parser, dispatcher, and REPL entry point
```

**Layer Responsibilities**

| Layer                       | Responsibility                                                 |
| --------------------------- | -------------------------------------------------------------- |
| `cli.py`                    | Parse SQL strings, dispatch to database, print results         |
| `core/database.py`          | Own all tables, manage transactions, reload tables on startup  |
| `core/table.py`             | Validate and execute all row operations, enforce constraints   |
| `core/transaction.py`       | Two-phase atomic commit, buffer operations, savepoints         |
| `query/expression.py`       | Evaluate WHERE expressions including subquery types            |
| `query/planner.py`          | Build join plans for all supported join types                  |
| `query/executor.py`         | Execute join plans and produce result rows                     |
| `storage/pager.py`          | Append, tombstone, and compact variable length rows on disk    |
| `storage/serializer.py`     | Convert rows to variable length binary and back                |
| `storage/schema_manager.py` | Write and read per-table `.schema` JSON files                  |
| `storage/btree.py`          | Sorted key-value tree with O(log n) search                     |
| `storage/hash_index.py`     | Hash based index with O(1) equality search                     |
| `storage/index_manager.py`  | Create, rebuild, and query B-Tree, hash, and composite indexes |
| `gui/`                      | PyQt6 desktop interface - editor, results, charts, ER diagram  |

---

## Getting Started

### Requirements

- Python 3.10+
- PyQt6 (GUI only)
- matplotlib (charts and ER diagram)

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
pytest tests/phase_1_test.py -v -s
pytest tests/phase_2_test.py -v -s
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

CREATE TABLE documents (
    id int PRIMARY KEY,
    title string,
    body text,
    thumbnail blob,
    settings json,
    manifest xml
);

ALTER TABLE employees ADD COLUMN bonus int DEFAULT 0;
ALTER TABLE employees DROP COLUMN bonus;
ALTER TABLE employees RENAME COLUMN salary TO pay;

TRUNCATE TABLE employees;
COMPACT TABLE employees;

RENAME TABLE employees TO staff;

CREATE VIEW high_earners AS SELECT name, salary FROM employees WHERE salary > 80000;
CREATE OR REPLACE VIEW high_earners AS SELECT name, salary FROM employees WHERE salary > 70000;
DROP VIEW high_earners;

EXPLAIN SELECT * FROM employees WHERE salary = 80000;
EXPLAIN SELECT dept_id, COUNT(*) FROM employees GROUP BY dept_id;

DROP TABLE users;
CREATE INDEX ON users (id);
CREATE HASH INDEX ON users (id);
CREATE INDEX ON employees (dept_id, salary);
```

**DML**

```sql
INSERT INTO users VALUES (1, 'Alice');
INSERT INTO documents VALUES (1, 'Notes', 'A long body of text with no length limit.', x'48656c6c6f', '{"theme": "dark"}', '<root><item>1</item></root>');

SELECT * FROM users;
SELECT DISTINCT dept_id FROM employees;
SELECT name AS employee, salary AS pay FROM employees;

SELECT * FROM employees WHERE id = 1;
SELECT * FROM employees WHERE salary BETWEEN 60000 AND 90000;
SELECT * FROM employees WHERE name LIKE 'A%';
SELECT * FROM employees WHERE dept_id IS NULL;
SELECT * FROM employees WHERE salary + 5000 > 100000;
SELECT * FROM employees WHERE dept_id IN (1, 2, 3);

SELECT dept_id, COUNT(*), COUNT(DISTINCT name), AVG(salary) FROM employees GROUP BY dept_id;
SELECT dept_id, COUNT(*) FROM employees GROUP BY dept_id HAVING COUNT(*) > 1;

SELECT name FROM employees WHERE dept_id IN (SELECT id FROM departments WHERE name = 'Engineering');
SELECT name FROM employees WHERE salary > ANY (SELECT salary FROM employees WHERE dept_id = 3);
SELECT name FROM employees WHERE salary > ALL (SELECT salary FROM employees WHERE dept_id = 3);
SELECT id FROM departments WHERE EXISTS (SELECT id FROM employees WHERE dept_id = 1);

SELECT name FROM departments UNION SELECT name FROM employees;
SELECT dept_id FROM employees WHERE salary > 70000 INTERSECT SELECT dept_id FROM employees WHERE dept_id = 1;
SELECT dept_id FROM employees EXCEPT SELECT dept_id FROM employees WHERE dept_id = 1;

SELECT * FROM employees INNER JOIN departments ON employees.dept_id = departments.id;
SELECT * FROM employees LEFT JOIN departments ON employees.dept_id = departments.id;
SELECT * FROM departments RIGHT JOIN employees ON departments.id = employees.dept_id;
SELECT * FROM employees FULL OUTER JOIN departments ON employees.dept_id = departments.id;
SELECT * FROM departments CROSS JOIN employees;
SELECT * FROM employees AS a INNER JOIN employees AS b ON a.dept_id = b.dept_id;

SELECT * FROM employees ORDER BY dept_id ASC, salary DESC LIMIT 5;

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
INSERT INTO employees VALUES (NULL, 1, 'Alice', 90000);
SAVEPOINT after_alice;
INSERT INTO employees VALUES (NULL, 1, 'Bob', 80000);
ROLLBACK TO SAVEPOINT after_alice;
RELEASE SAVEPOINT after_alice;
COMMIT;
```

## Data Types

| Type           | Python equivalent        | Storage size                          |
| -------------- | ------------------------ | ------------------------------------- |
| `int`          | `int`                    | 4 bytes signed                        |
| `bigint`       | `int`                    | 8 bytes signed                        |
| `float`        | `float`                  | 8 bytes IEEE 754 double               |
| `boolean`      | `bool`                   | 1 byte                                |
| `string`       | `str`                    | 256 bytes fixed width                 |
| `varchar(n)`   | `str`                    | n bytes fixed width                   |
| `char(n)`      | `str`                    | n bytes fixed width                   |
| `decimal(p,s)` | `Decimal`                | 8 bytes scaled int64                  |
| `money`        | `Decimal`                | 8 bytes scaled int64                  |
| `date`         | `date`                   | 4 bytes signed                        |
| `datetime`     | `datetime`               | 8 bytes signed                        |
| `timestamp`    | `datetime`               | 8 bytes signed                        |
| `time`         | `time`                   | 4 bytes signed                        |
| `text`         | `str`                    | variable length, 4 byte length prefix |
| `blob`         | `bytes`                  | variable length, 4 byte length prefix |
| `json`         | `str`, validated as JSON | variable length, 4 byte length prefix |
| `xml`          | `str`, validated as XML  | variable length, 4 byte length prefix |

`BLOB` values are entered in SQL using hex literal syntax, for example `x'48656c6c6f'`. `JSON` and `XML` columns are validated for well formed content on insert and update, and rejected with an error if the content does not parse.

---

## Storage Format

Every row on disk has this structure:

- 1 byte tombstone flag, `0x00` for alive and `0xFF` for deleted
- 4 byte big endian length prefix for the row content
- the row content itself, produced by the serializer

Each column inside the row content has a 1 byte null flag followed by its value bytes. Fixed width types like `int` and `boolean` always occupy the same number of bytes. Variable length types like `text`, `blob`, `json`, and `xml` are stored with their own 4 byte length prefix inside the row content, allowing a single row to mix fixed and variable width columns freely.

Deletes write the tombstone byte in place at the row's stored offset, which is a constant time operation regardless of table size. `COMPACT TABLE` reclaims space by rewriting the file with only the rows that are still alive.

---

## Constraints

| Constraint              | Behaviour                                                                    |
| ----------------------- | ---------------------------------------------------------------------------- |
| `PRIMARY KEY`           | UNIQUE + NOT NULL, single column or composite                                |
| `COMPOSITE PRIMARY KEY` | Uniqueness enforced across the combination of columns                        |
| `UNIQUE`                | No duplicate values, single column or composite                              |
| `NOT NULL`              | Rejects NULL on insert and update                                            |
| `DEFAULT`               | Substituted when value is omitted or NULL                                    |
| `CHECK`                 | Arbitrary comparison evaluated on insert and update                          |
| `AUTO_INCREMENT`        | Counter persisted to schema, never reused after restart                      |
| `FOREIGN KEY`           | Value must exist in referenced table, enforced on insert, update, and commit |
| `ON DELETE CASCADE`     | Child rows deleted automatically when parent is deleted                      |
| `ON UPDATE CASCADE`     | Child FK values updated automatically when parent PK changes                 |
| `JSON` validity         | Value must parse as well formed JSON                                         |
| `XML` validity          | Value must parse as well formed XML                                          |
| Duplicate rows          | Exact duplicate rows always rejected                                         |

---

## Persistence

Each table produces two files in the `data/` directory:

| File                | Contents                                                                          |
| ------------------- | --------------------------------------------------------------------------------- |
| `table_name.db`     | Variable length binary row data with tombstone flags                              |
| `table_name.schema` | JSON - columns, types, constraints, indexes, foreign keys, auto increment counter |

On startup the database scans `data/` for `.schema` files and reloads all tables automatically, rebuilding B-Tree, hash, and composite indexes and restoring all constraint definitions. Row byte offsets are rebuilt in memory on load so deletes can target exact row positions without a full file scan.

---

## Transactions

PyBase uses a two-phase atomic commit model:

- `BEGIN` starts buffering `INSERT`, `UPDATE`, and `DELETE` operations
- `COMMIT` runs Phase 1 (validate all operations) then Phase 2 (apply all operations)
- If Phase 1 finds any violation, nothing is applied and the transaction is auto-cancelled
- `ROLLBACK` discards the buffer - nothing is written
- `SAVEPOINT name` creates a named restore point inside the active transaction
- `ROLLBACK TO SAVEPOINT name` undoes back to that point without ending the transaction
- `RELEASE SAVEPOINT name` discards a savepoint once it is no longer needed
- `SELECT` always reads live committed data, even inside a transaction
- `DROP TABLE` and `DROP DATABASE` are blocked inside a transaction
- Nested transactions are not supported

---

## GUI

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
