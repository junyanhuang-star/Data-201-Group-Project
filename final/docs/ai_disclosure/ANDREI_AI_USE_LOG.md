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

## Additional prompt used for implementation comparison and loader review

The following prompt was used for the later stage of comparing the current
implementation with the teammate's `/jun` branch, reviewing the merged schema,
creating a loader, and updating this disclosure. It is included verbatim for
bookkeeping rather than summarized:

```text
The next task is to do a more in depth comparison between my approach and my teammate’s approach that is on the /jun branch. After discussing together as a team, it primarily agreed that our approaches were the same with the difference being slight naming conventions, and possible differences in implementations for data cleaning. The first task to do another comparison that focuses on comparing implementation wise and output the findings onto a new MD file. All MD files should be added to a folder so that it is less cluttered on the branch.

The second task is to do a complete analysis on the relational schema that was created with our approach and on my teammate’s approach. During the meeting, it was agreed that their was not much differences in the approach, so it is okay for the two to be merged. With both being acceptable, the merged version should contain aspects from both implementations that outputs the most correct implementation.

As AI is being used to finalize and validate the relational schema with the entire CSV, this needs to be properly disclosed in the AI usage. The initial decision making of creating the 3NF relational schema was assisted with using AI. AI was not simply used to take the CSV and output a 3NF, but instead it was asked to analyze the contents of each row and explain why certain dependencies that seem reasonable would not work due to the actual contents of each entry. For example, as I have taken CS131, I am aware that bash commands can be used to find certain statistics like unique values per column. However, I could not immediately figure out how to write the bash command to output this finding, so AI was used. As a team, we felt that using AI to help come up with bash commands to understand our dataset was an acceptable use of AI as bash is outside the scope of the class.

In addition, during the meeting it was agreed that a loader (similarly to how it was done in /jun) would be used to import the rows from the CSV to the finalized tables. With the given topics discussed in class, we found that loading a CSV onto our tables in MySQL Workbench was not specifically covered in the course, so we felt that the approach to load the dataset can be done with implementations that might be out of scope of the class.

The next task is to create a loader class that aligns with the constraints for our approach, meaning that the loader should utilize as much covered course contents as possible, so that if it is usable and decided to be used for submission, a proper writeup from our team can be done explaining our understanding of the implementation and full disclosure of where the implementation came from. The AI disclosure should be updated explaining that the loader is likely out of scope of the class, but we felt that it was the least tedious way to clean and load all of the data onto the workbench.

The loader implementation does not necessarily need to be the same as the implementation done in /jun as differences should be considered if there is an approach that uses concepts tied closely to what has been covered in the course already. In the end, the loader implementation will be properly disclosed to be assisted with AI.

A summary of what needs to be added, differences in implementation approaches between this and teammates, data filtering with the given constraints, data import with the given constraints, and updates to AI disclosure. This entire prompt will need to be included in the AI disclosure to demonstrate how AI was used for this stage of the project.
```

## What AI assisted with in this stage

For this stage, AI assistance was used to:

- compare the current files with the teammate's `/jun` files at the level of
  parsing, ID assignment, staging, SQL loading, and validation;
- identify implementation gaps such as the missing foreign-key resolution step,
  stale history-column checks, and last-row metadata handling;
- draft `IMPLEMENTATION_COMPARISON.md` and `MERGED_SCHEMA_REVIEW.md`;
- draft `load_3nf.py`, a two-pass loader that was then run against the complete
  attached CSV and checked for a 28-column header, metadata consistency,
  deterministic dimensions, history rows, utility rows, and quality issues;
- explain that CSV loading is an import/orchestration step outside the main
  lecture DDL, even though the generated SQL still uses ordinary table and
  `LOAD DATA LOCAL INFILE` operations.

The loader was not produced by simply asking AI to convert the CSV into a
schema. It uses the already-reviewed schema, the project-note interpretations,
the existing Python normalization functions, and the teammate comparison as
constraints. The team must still inspect, rewrite, test, and disclose any part
that it adopts.

## Student's final disclosure note

I got those outputs, can I confirm that the tasks have all been handled now. I will review the implementations. I want to clarify if I have given my ai disclosure notes on all of the generated code. I assume that the loader will likely be used (maybe not this exact) to populate the tables for our project. This will definitely be disclosed and mentioned in the final submission. The data preparation stage heavily relied on AI assistance to implement code that was not explicitly covered in the course. However, the future steps of the project will be more aligned with course concepts as it requires using SQL queries to make sense of the dataset. These future phases will have way less AI assistance as it requires demonstrating exact concepts from class and should not be generated by AI.
