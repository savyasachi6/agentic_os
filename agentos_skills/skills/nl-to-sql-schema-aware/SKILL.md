# nl-to-sql-schema-aware

Translate natural language to SQL queries while respecting schema structure and relationships.

## Instructions

### Overview
This skill guides the translation of natural language questions into valid SQL statements by leveraging database schema awareness. The goal is to produce syntactically correct and logically accurate queries based on specific table and column metadata provided in the context.

### Step-by-Step Instructions

1. **Analyze the Schema**: Carefully examine the provided Data Definition Language (DDL) or schema summary. Note table names, column names, data types, and primary/foreign key relationships. Understanding these connections is critical for multi-table queries.
2. **Identify User Intent**: Determine the core objective of the request. Is the user looking for a list (SELECT *), a specific count (COUNT), a total (SUM), or a filtered subset (WHERE)?
3. **Map Entities**: Map natural language nouns to specific schema elements. For instance, if a user asks for 'sales people' but the table is named `employees` with a `job_title` of 'Sales Rep', map the logic accordingly.
4. **Establish Join Logic**: If the required data resides in multiple tables, identify the shortest path between them using foreign keys. Always use explicit `JOIN` syntax (e.g., `INNER JOIN`, `LEFT JOIN`) rather than comma-separated tables.
5. **Synthesize the SQL**: Construct the query using standard SQL. Use table aliases (e.g., `u` for `users`) to keep the query readable and avoid column ambiguity.
6. **Validate and Refine**: Ensure that data types match (e.g., wrapping strings in single quotes) and that all columns in the `SELECT` clause that are not part of an aggregate function are included in a `GROUP BY` clause if needed.

### Examples

**Example 1: Simple Filtering and Sorting**
- *Prompt*: 'Get the names of the 5 most expensive products.'
- *SQL*: `SELECT product_name, price FROM products ORDER BY price DESC LIMIT 5;`

**Example 2: Join with Aggregation**
- *Prompt*: 'Show total order amounts for each customer in London.'
- *SQL*:
```sql
SELECT c.customer_name, SUM(o.total_amount) AS total_spent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE c.city = 'London'
GROUP BY c.customer_name;
```

### Best Practices
- **Use Aliases**: Always use short, descriptive table aliases for clarity.
- **Handle Nulls**: Use `COALESCE` or `IS NOT NULL` if the user implies they only want records with valid data.
- **Case Sensitivity**: Be mindful of whether the target database is case-sensitive for string comparisons and use `LOWER()` if unsure.