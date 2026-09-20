# Short-Term Rental Platform — Database Design

A conceptual-to-logical database design project for a short-term rental platform (think Airbnb-style), built as a course assignment. Includes a Chen-notation ER diagram, the mapped relational schema, working MySQL scripts with sample data, and the reverse-engineered logical diagram.

## Overview

The platform connects **hosts** who list **properties** with **guests** who make **bookings**. The design captures:

- Hosts with multiple phone numbers and spoken languages (multivalued attributes)
- Properties with a composite address (street, city, postal code, country)
- Guests with multiple phone numbers
- Bookings linking one guest to one property, with dates, amount, payment method, and status

## Repository Structure

```
.
├── README.md
├── schema.sql              # CREATE DATABASE + CREATE TABLE statements (MySQL 8.0)
├── sample_data.sql         # Sample INSERT statements for all 7 tables
└── diagrams/
    ├── er_chen_notation.png     # Q1: Conceptual ER diagram (Chen's notation)
    ├── logical_diagram.png      # Q3: Reverse-engineered logical diagram (PK/FK)
    └── eer_diagram.png          # Q4: EER diagram (employee specialization example)
```

## Entity-Relationship Diagram

![ER Diagram](diagrams/er_chen_notation.png)

**Entities:** HOST, PROPERTY, GUEST, BOOKING
**Relationships (all 1:N):** HOST *owns* PROPERTY · PROPERTY *is for* BOOKING · GUEST *makes* BOOKING

## Relational Schema

```
Host(host_id, full_name, email, join_date)
Host_Phone(host_id, phone_number)                 — FK host_id → Host
Host_Language(host_id, language)                  — FK host_id → Host
Property(property_id, host_id, name, description,
         street, city, postal_code, country,
         max_guests, bedrooms, bathrooms)          — FK host_id → Host
Guest(guest_id, full_name, email)
Guest_Phone(guest_id, phone_number)                — FK guest_id → Guest
Booking(booking_id, guest_id, property_id,
        booking_date, check_in_date, check_out_date,
        num_guests, total_amount, payment_method, status)
                                                    — FK guest_id → Guest
                                                    — FK property_id → Property
```

Multivalued attributes (phone numbers, languages) are normalized into their own tables to satisfy 1NF; the composite `Address` attribute is flattened into plain columns on `Property`.

## Logical Diagram

![Logical Diagram](diagrams/logical_diagram.png)

## Getting Started

1. Install MySQL Server and open MySQL Workbench (or any MySQL client).
2. Run `schema.sql` to create the `rental_platform` database and all tables.
3. Run `sample_data.sql` to populate the tables with sample records.
4. Optionally, use **Database → Reverse Engineer** in Workbench on the `rental_platform` schema to regenerate the logical diagram.

```bash
mysql -u root -p < schema.sql
mysql -u root -p < sample_data.sql
```

## EER Diagram (Bonus Example)

An additional example EER diagram modeling employee role hierarchies (specialization/generalization, disjoint vs. overlapping constraints) is included for reference.

![EER Diagram](diagrams/eer_diagram.png)

## License

This project was created for educational purposes as part of a database design course assignment.
