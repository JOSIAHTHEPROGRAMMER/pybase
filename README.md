# PyBase

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)
![Coverage](https://img.shields.io/badge/Coverage-60%25%20Required-brightgreen)
[![Build and Test](https://github.com/JOSIAHTHEPROGRAMMER/pybase/actions/workflows/tests.yml/badge.svg)](https://github.com/JOSIAHTHEPROGRAMMER/pybase/actions/workflows/tests.yml)
![GUI](https://img.shields.io/badge/GUI-PyQt6-41CD52?style=flat&logo=qt&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-Binary%20%2B%20JSON-orange?style=flat)

PyBase is a minimal relational database engine built from scratch in Python, without any external libraries except PyQt6 and matplotlib for the GUI. It implements real database internals: custom variable length binary storage with tombstone deletes, B-Tree and hash indexing, schema persistence, a full constraint system, transactions with savepoints, a complete query system with joins and subqueries, DDL operations, views, user defined composite types, and stored procedures.

## Preview

<img width="1918" height="1012" alt="PyBase GUI" src="https://github.com/user-attachments/assets/7e0a8dfa-d84a-4d62-a828-9ac1ff241972" />

## Features

**Core Engine**

Full CRUD with `CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `DROP TABLE`, and `DROP DATABASE`. SQL-like syntax with case-insensitive keywords and all column names normalised to lowercase. Rows are stored in binary `.db` files using a variable length tombstone format, and schemas in `.schema` JSON files. B-Tree indexing via `CREATE INDEX` gives O(log n) equality lookups, auto-maintained on insert, update, and delete. Hash indexing via `CREATE HASH INDEX` gives O(1) equality lookups. Composite indexes are supported across multiple columns. Multi-statement scripts separated by semicolons are supported, including scripts containing a `CREATE PROCEDURE` body whose own internal semicolons are correctly preserved rather than treated as statement separators. All SQL parsing and dispatch logic is shared between the CLI and the GUI through one execution layer, so both surfaces behave identically.

**Storage Engine**

Rows are stored with a one byte tombstone flag and a four byte length prefix, allowing variable length data like `TEXT` and `BLOB` to live alongside fixed width types in the same file. Deletes write a tombstone byte in place rather than rewriting the whole file, making deletes a constant time operation regardless of table size. `COMPACT TABLE` reclaims space from tombstoned rows by rewriting the file with only live rows. In memory row offsets are tracked so deletes always target the exact byte position of a row without a full file scan.

**Constraints**

`PRIMARY KEY` enforces UNIQUE + NOT NULL on single or composite columns. `UNIQUE`, `NOT NULL`, `DEFAULT`, and `CHECK` are all enforced on insert and update. `AUTO_INCREMENT` persists its counter to the schema so values are never reused after a restart, and the counter is never advanced on a failed insert. Foreign keys use `REFERENCES` syntax and are enforced on insert, update, and two-phase commit. `ON DELETE CASCADE` and `ON UPDATE CASCADE` are both supported. Exact duplicate rows are always rejected.

**User Defined Types and Procedures**

`CREATE TYPE` defines a named composite type from a fixed set of typed fields, similar to a PostgreSQL composite type. Composite type columns are stored internally as validated JSON, entered as a JSON object literal, and checked field by field on insert and update, including exact field matching and nested composite types that reference other already defined types. `DROP TYPE` is blocked while the type is in use by a column or referenced by another type. `CREATE PROCEDURE` defines a named, parameterised sequence of SQL statements executed with `CALL`. Procedure bodies are stored as text and are not validated against real tables or columns until they are actually called, matching standard deferred name resolution behaviour. `SET` assignments in `UPDATE` support arithmetic, both self referential (`salary = salary + amount`, resolved per row against the current value) and literal (`salary = 50000 + 1000`, evaluated once at parse time).

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
- `EXPLAIN` correctly reports B-Tree index scans, hash index scans, and full table scans
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
- Export query results to CSV
- Bar, line, pie, scatter, and histogram chart tab via matplotlib
- Live ER diagram tab with crow's foot notation and FK relationship lines
- Schema browser with table row counts, column types, and constraint tags (PK, FK, UQ, IDX)
- Schema browser right click context menu - rename, truncate, compact, and drop a table, or create a B-Tree or hash index on a column
- Column statistics on double click or via the context menu - count, nulls, min/max/avg for numeric columns, distinct count for others, and a value breakdown for ENUM columns
- Click a table in the schema browser to load `SELECT * FROM table_name;` into the editor
- Non-modal query plan window for `EXPLAIN`, so the plan can stay open alongside the editor
- Transaction status indicator - green dot when a transaction is active
- `DROP TABLE` and `DROP DATABASE` confirmation dialogs
- Error and status messages are selectable and copyable
- Dark Neon theme - `#0f0f0f` background, `#00e599` accent

---

## Architecture

```
pybase/
├── core/
│   ├── database.py         # Database registry, table lifecycle, views, custom types, procedures, transaction management
│   ├── table.py             # Table operations, constraint enforcement, query execution, DDL methods
│   └── transaction.py       # Two-phase atomic commit, savepoints, BEGIN/COMMIT/ROLLBACK
├── gui/
│   ├── main.py               # QApplication entry point
│   ├── main_window.py        # MainWindow, assembles all panels
│   ├── panels/
│   │   ├── chart.py          # Bar, line, pie, scatter, histogram charts with NULL handling
│   │   ├── editor.py         # SQL editor, syntax highlighting, history, run button
│   │   ├── er_diagram.py     # Live ER diagram with crow's foot FK notation
│   │   ├── results.py        # Tabbed results panel, CSV export
│   │   └── schema.py         # Schema browser, context menu, column stats, click-to-query
│   └── widgets/
│       ├── column_stats_dialog.py  # Non-modal column statistics window
│       ├── explain_dialog.py       # Non-modal EXPLAIN query plan window
│       ├── font.py                 # Monospace font fallback helper
│       ├── highlighter.py          # SQL syntax highlighter
│       ├── history.py              # Query history dropdown with persistence
│       └── status_bar.py           # Transaction status indicator
├── query/
│   ├── dispatch.py          # Shared statement execution layer used by both the CLI and the GUI
│   ├── expression.py        # Full expression evaluator - comparisons, logical, arithmetic, bitwise, subqueries
│   ├── planner.py           # Join planning for INNER, LEFT, RIGHT, FULL OUTER, CROSS, SELF joins
│   ├── executor.py          # Executes the join plan and produces result rows
│   ├── sql_parser.py        # Pure SQL parsing layer, no execution or database access
│   └── utils.py             # Shared query helpers, aggregate detection
├── storage/
│   ├── btree.py             # B-Tree and BTreeNode data structures
│   ├── hash_index.py        # Hash index for O(1) equality lookups
│   ├── index_manager.py     # Owns and manages B-Tree, hash, and composite indexes per table
│   ├── page.py               # Low-level page abstraction and page layout helpers
│   ├── pager.py              # Variable length row file read/write with tombstone deletes, compaction, and WAL handling
│   ├── schema_manager.py     # JSON schema persistence per table
│   └── serializer.py         # Row serialization to/from variable length binary
├── tests/
│   ├── phase_1_test.py       # Comprehensive Phase 1 test suite (64 tests)
│   ├── phase_2_test.py       # Phase 2 test suite - tombstone deletes, TEXT/BLOB/JSON/XML, compaction
│   ├── phase_3_test.py       # Phase 3 test suite - ENUM/UUID/smallint/tinyint, composite types, stored procedures
│   ├── cli_parser_test.py    # SQL parser unit tests, isolated from full database integration
│   └── gui_test.py           # GUI integration tests using pytest-qt
└── cli.py                    # Thin REPL loop, delegates parsing and execution to query/sql_parser.py and query/dispatch.py
```

**Layer Responsibilities**

| Layer                       | Responsibility                                                                                    |
| --------------------------- | ------------------------------------------------------------------------------------------------- |
| `cli.py`                    | Read input in a loop, delegate each statement to the dispatch layer                               |
| `query/sql_parser.py`       | Parse SQL strings into structured data, no database access                                        |
| `query/dispatch.py`         | Execute a parsed statement against the database, shared by CLI and GUI                            |
| `core/database.py`          | Own all tables, views, custom types, and procedures; manage transactions; reload state on startup |
| `core/table.py`             | Validate and execute all row operations, enforce constraints                                      |
| `core/transaction.py`       | Two-phase atomic commit, buffer operations, savepoints                                            |
| `query/expression.py`       | Evaluate WHERE expressions including subquery types                                               |
| `query/planner.py`          | Build join plans for all supported join types                                                     |
| `query/executor.py`         | Execute join plans and produce result rows                                                        |
| `storage/page.py`           | Define page-level storage layout and page helpers                                                 |
| `storage/pager.py`          | Append, tombstone, compact rows on disk, and manage WAL state                                     |
| `storage/serializer.py`     | Convert rows to variable length binary and back                                                   |
| `storage/schema_manager.py` | Write and read per-table `.schema` JSON files                                                     |
| `storage/btree.py`          | Sorted key-value tree with O(log n) search                                                        |
| `storage/hash_index.py`     | Hash based index with O(1) equality search                                                        |
| `storage/index_manager.py`  | Create, rebuild, and query B-Tree, hash, and composite indexes                                    |
| `gui/`                      | PyQt6 desktop interface - editor, results, charts, ER diagram, schema browser                     |

---

## Getting Started

### Requirements

- Python 3.10+
- PyQt6 (GUI only)
- matplotlib (charts and ER diagram)
- pytest, pytest-cov, pytest-qt (tests only)

```bash
pip install PyQt6 matplotlib pytest pytest-cov pytest-qt
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
pytest tests/ -v -s
```

Or run individual suites:

```bash
pytest tests/phase_1_test.py -v -s
pytest tests/phase_2_test.py -v -s
pytest tests/phase_3_test.py -v -s
pytest tests/cli_parser_test.py -v -s
pytest tests/gui_test.py -v -s
```

GUI tests run headless via Qt's offscreen platform plugin, set automatically at the top of `gui_test.py`. If they fail to launch in an unfamiliar environment, run with `QT_QPA_PLATFORM=offscreen` set explicitly.

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

CREATE TABLE orders (
    id int PRIMARY KEY AUTO_INCREMENT,
    status enum(pending,shipped,delivered),
    tracking_id uuid,
    priority tinyint,
    units smallint
);

CREATE TYPE address AS (street varchar(50), city varchar(30), zip varchar(10));
CREATE TYPE contact AS (email varchar(50), home address);

CREATE TABLE people (
    id int PRIMARY KEY AUTO_INCREMENT,
    home_address address,
    info contact
);

DROP TYPE contact;

CREATE PROCEDURE give_raise(emp_id int, amount int) AS BEGIN
UPDATE employees SET salary = salary + amount WHERE id = emp_id;
END;

DROP PROCEDURE give_raise;

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
INSERT INTO orders VALUES (NULL, 'pending', '550e8400-e29b-41d4-a716-446655440000', 3, 1200);
INSERT INTO people VALUES (NULL, '{"street": "Main St", "city": "Springfield", "zip": "12345"}', NULL);

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
UPDATE employees SET salary = salary + 5000 WHERE id = 1;
DELETE FROM employees WHERE id = 1;

CALL give_raise(1, 5000);
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

| Type                              | Python equivalent                                | Storage size                          |
| --------------------------------- | ------------------------------------------------ | ------------------------------------- |
| `int`                             | `int`                                            | 4 bytes signed                        |
| `bigint`                          | `int`                                            | 8 bytes signed                        |
| `smallint`                        | `int`                                            | 2 bytes signed                        |
| `tinyint`                         | `int`                                            | 1 byte signed                         |
| `float`                           | `float`                                          | 8 bytes IEEE 754 double               |
| `boolean`                         | `bool`                                           | 1 byte                                |
| `string`                          | `str`                                            | 256 bytes fixed width                 |
| `varchar(n)`                      | `str`                                            | n bytes fixed width                   |
| `char(n)`                         | `str`                                            | n bytes fixed width                   |
| `enum(v1,v2,...)`                 | `str`, restricted to the list                    | fixed width, sized to longest value   |
| `uuid`, `uniqueidentifier`        | `str`, standard UUID format                      | 16 bytes                              |
| `decimal(p,s)`                    | `Decimal`                                        | 8 bytes scaled int64                  |
| `money`                           | `Decimal`                                        | 8 bytes scaled int64                  |
| `date`                            | `date`                                           | 4 bytes signed                        |
| `datetime`                        | `datetime`                                       | 8 bytes signed                        |
| `timestamp`                       | `datetime`                                       | 8 bytes signed                        |
| `time`                            | `time`                                           | 4 bytes signed                        |
| `text`                            | `str`                                            | variable length, 4 byte length prefix |
| `blob`                            | `bytes`                                          | variable length, 4 byte length prefix |
| `json`                            | `str`, validated as JSON                         | variable length, 4 byte length prefix |
| `xml`                             | `str`, validated as XML                          | variable length, 4 byte length prefix |
| user defined type (`CREATE TYPE`) | `str`, validated field by field against the type | stored as `json`, variable length     |

`BLOB` values are entered in SQL using hex literal syntax, for example `x'48656c6c6f'`. `JSON`, `XML`, and user defined composite type columns are validated for well formed and, for composite types, structurally correct content on insert and update, and rejected with an error if the content does not match. `ENUM` values must exactly match one of the values declared at `CREATE TABLE` time. `UUID` values must be a valid standard UUID string.

---

## Storage Format

Every row on disk has this structure:

- 1 byte tombstone flag, `0x00` for alive and `0xFF` for deleted
- 4 byte big endian length prefix for the row content
- the row content itself, produced by the serializer

Each column inside the row content has a 1 byte null flag followed by its value bytes. Fixed width types like `int` and `boolean` always occupy the same number of bytes. Variable length types like `text`, `blob`, `json`, and `xml` are stored with their own 4 byte length prefix inside the row content, allowing a single row to mix fixed and variable width columns freely. User defined composite types are stored using the same `json` variable length format, with structural validation applied at the `Table` layer rather than the serializer.

Deletes write the tombstone byte in place at the row's stored offset, which is a constant time operation regardless of table size. `COMPACT TABLE` reclaims space by rewriting the file with only the rows that are still alive.

---

## Constraints

| Constraint              | Behaviour                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------ |
| `PRIMARY KEY`           | UNIQUE + NOT NULL, single column or composite                                                          |
| `COMPOSITE PRIMARY KEY` | Uniqueness enforced across the combination of columns                                                  |
| `UNIQUE`                | No duplicate values, single column or composite                                                        |
| `NOT NULL`              | Rejects NULL on insert and update                                                                      |
| `DEFAULT`               | Substituted when value is omitted or NULL, quoted values with embedded commas are parsed correctly     |
| `CHECK`                 | Arbitrary comparison evaluated on insert and update                                                    |
| `AUTO_INCREMENT`        | Counter persisted to schema, never reused after restart, never advanced on a failed insert             |
| `FOREIGN KEY`           | Value must exist in referenced table, enforced on insert, update, and commit                           |
| `ON DELETE CASCADE`     | Child rows deleted automatically when parent is deleted                                                |
| `ON UPDATE CASCADE`     | Child FK values updated automatically when parent PK changes                                           |
| `JSON` validity         | Value must parse as well formed JSON                                                                   |
| `XML` validity          | Value must parse as well formed XML                                                                    |
| `ENUM` validity         | Value must exactly match one of the declared allowed values                                            |
| `UUID` validity         | Value must be a valid standard UUID string                                                             |
| Composite type validity | Value must be a JSON object matching the type's fields and field types exactly, including nested types |
| Duplicate rows          | Exact duplicate rows always rejected                                                                   |

---

## Persistence

Each table produces a data file, a schema file, and a write-ahead log (WAL) in the `data/` directory. Views, user defined types, and stored procedures are persisted database-wide rather than per table. The WAL records pending changes for durability and crash recovery; it is replayed on startup before schemas are loaded.

| File                | Contents                                                                          |
| ------------------- | --------------------------------------------------------------------------------- |
| `table_name.db`     | Variable length binary row data with tombstone flags                              |
| `table_name.schema` | JSON - columns, types, constraints, indexes, foreign keys, auto increment counter |
| `table_name.wal`    | Append-only log of transactional changes for recovery and replay                  |
| `views.json`        | JSON - all view definitions, database-wide                                        |
| `custom_types.json` | JSON - all user defined composite type definitions, database-wide                 |
| `procedures.json`   | JSON - all stored procedure definitions and parameter lists, database-wide        |

On startup the database scans `data/` for `.schema` files and reloads all tables automatically, rebuilding B-Tree, hash, and composite indexes and restoring all constraint definitions. Views, custom types, and procedures are reloaded from their respective JSON files. Row byte offsets are rebuilt in memory on load so deletes can target exact row positions without a full file scan. `DROP DATABASE` clears all tables, views, custom types, procedures, and query history, both in memory and on disk.

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

## User Defined Types and Stored Procedures

`CREATE TYPE` defines a named composite type made of typed fields. Fields must be a JSON-safe scalar type (`int`, `float`, `boolean`, `string`, `varchar`, `char`, `text`) or another already defined custom type, allowing nested composite types. Columns declared with a custom type are stored internally as `json` and validated field by field, including exact field name matching and recursive validation of nested types, on every insert and update. `DROP TYPE` is refused if the type is currently used by any table column or referenced as a field inside another type.

`CREATE PROCEDURE` defines a named procedure with a typed parameter list and a `BEGIN ... END` body containing one or more SQL statements. The body is stored as text and is not validated against real tables or columns until it is called, matching standard deferred name resolution behaviour used by production databases. `CALL` substitutes each argument for its parameter name across every statement in the body, then executes each statement in order through the same execution layer used for ordinary top-level statements, so any statement type is valid inside a procedure body. A single summary message reports how many statements ran. `DROP PROCEDURE` removes a procedure immediately.

---

## GUI

```bash
python -m gui.main
```

| Panel          | Description                                                                                                            |
| -------------- | ---------------------------------------------------------------------------------------------------------------------- |
| SQL Editor     | Write and run SQL with syntax highlighting and Ctrl+Enter shortcut                                                     |
| Query History  | Dropdown of previous queries, persisted across sessions                                                                |
| Results Table  | Tabbed panel showing query results with row numbers, exportable to CSV                                                 |
| Chart Tab      | Auto-renders bar, line, pie, scatter, or histogram from SELECT results                                                 |
| ER Diagram Tab | Live entity-relationship diagram with crow's foot FK notation                                                          |
| Schema Browser | All tables, column types, constraint tags, live row counts, right click actions, and column statistics on double click |
| Query Plan     | Non-modal window showing the `EXPLAIN` output for a query                                                              |
| Status Bar     | Green indicator when a transaction is active                                                                           |

Clicking a table in the schema browser loads `SELECT * FROM table_name;` into the editor. Right clicking a table offers refresh, rename, truncate, compact, and drop, with confirmation dialogs on destructive actions. Right clicking or double clicking a column offers index creation and a column statistics window showing count, null count, min/max/avg for numeric columns, distinct count for other types, and a per-value breakdown for `ENUM` columns.
