# AI Use Log

This file records the AI assistance used as a reference during the planning and review of the SF Rent Board database project. It is an academic-integrity record, not a statement that the generated material should be submitted unchanged.

## Session information

- Date of initial prompt: September 26, 2026
- Tool: Codex desktop
- Model: Record the exact model identifier shown in the application settings or conversation metadata. It is not inferred here.
- Student responsibility: The team must review, understand, verify, rewrite, and modify any ideas or code used in the final project.

## Purpose of the AI assistance

AI assistance was used as a supplementary planning and coding resource for:

- interpreting the source columns and unique-value findings;
- comparing an initial relational-schema idea with a teammate’s implementation;
- discussing 1NF, 2NF, and 3NF decisions;
- organizing possible lookup, fact, child, and junction tables;
- drafting example Python preprocessing and MySQL `CREATE TABLE` statements;
- explaining MySQL Workbench ER-diagram relationships and visual editing;
- creating study notes and comparison documents for team review.

The generated Markdown files, SQL files, Python files, explanations, ER-diagram guidance, and other material are reference resources. They are not intended to be submitted as-is.

## Initial prompt used

The following is the initial prompt that began the work on the relational schema, preprocessing, table creation, and ER-diagram task:

```text
I have attached the relevant files describing my notes for the database course, so that you can get the constraints of what has been covered so far and what should be added. I have also attached the lecture slides that contained the requirements of the semester project, with the focus of this session is to focus on preparing for the mid presentation.

My task right now is to take the dataset on SF Housing and Buildings records, put it in 3NF, and create a relational schema. I have attached my document notes of what I found so far about each column (with specifically being the unique values of each column, which I plan to use to preprocess/clean the data for use). Once a relational schema is created, I am tasked to create the corresponding CREATE TABLES for the relational schema, and generate an ER diagram on MySQL Workbench.

Therefore, the first step is to confirm what the attributes represent, if there is any additional information we can get from it (ex. taking POINT and creating additional attributes of it representing longitude, latitude, altitude, addresses, streets, etc.). The search for additional information would likely be done on the string entries that could be spliced for specific information.

The next step is to take the confirmed attributes, and decide on a 3NF. Work has been done to look for a 3NF but there is room to improve on it and suggestions are welcome.

The next step is to finalize the relational schema on the decided 3NF, which will be used to create the tables. The constraints of each type (INT, VARCHAR, DATE, etc.) needs to be determined.

Finally, an approach on how to preprocess the data needs to be handled. Initially, I thought of doing these outside of SQL and data preprocess similarly to how it is done when cleaning a dataset on a colab notebook/ jupyter notebook. This would have involved going through each of the entries and either fixing values, making values consistent, or removing invalid entries. However, the professor has mentioned that SQL queries, JOINS, etc. can be used for the data preprocess step. If this is the more suitable procedure, then creating SQL queries to make sure that the correct formatted data is populated into the tables is needed.

As for determining what values are appropriate, I noticed that there are a lot of categorical data, data ranges, etc. which can be updated to be consistent so when we use these tables for data visualizing. The inconsistent inputs that represent the same values will be grouped together. For example, in bathroom_count, there are multiple values which essentially just represent 1. All of these should be grouped together and counted as 1.

My teammate has done an initial approach on creating a 3NF, creating a relational schema and the corresponding tables. He has also included data preprocessing. The goal is to not copy the existing approach, but take what I have found so far, and add on any short ends that my teammate has not considered. In other words, the github repo link was provided as a reference of what has been done and is not finalized. What you will be helping me is my own implementation of this task.

Related material:
https://data.sfgov.org/Housing-and-Buildings/Rent-Board-Housing-Inventory/gdc7-dmcn/about_data
https://github.com/junyanhuang-star/Data-201-Group-Project/tree/jun/house
https://docs.google.com/document/d/186uAPX8zzfk4rKA6Bb6tGAvaTwTnXhmr8uKb2heJQFU/edit?usp=sharing
```

## Later reference materials

The work also used or discussed these materials during later review:

- `DATA201_Lecture1_Introduction (1).pdf`
- `DATA201 Project Notes.pdf`
- `Rent_Board_Housing_Inventory_20260927.csv`
- the teammate’s `jun/house` branch and commit history;
- the MySQL Workbench ER diagram;
- `music_schema (1).sql` as a formatting/commenting example.

The project notes and attached CSV were used to correct an earlier source-version mismatch. The final team implementation should use one verified CSV export and rerun its own unique-value and dependency checks.

## Disclosure statement

The team will not submit the generated files as-is. If any idea, code, schema decision, SQL comment, preprocessing approach, or ER-diagram structure is adopted, the team will understand it, verify it against the source data and course material, make appropriate changes, and disclose the relevant AI assistance. The team remains responsible for the final work and its explanation.
