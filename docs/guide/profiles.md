# Profile Management Guide

## Overview

Fast-App stores user profiles to tailor resumes and cover letters. Profiles contain your work history, education, skills, and preferences. With multi-user support, each user can have multiple profiles (e.g., "General", "Engineering Lead", "Data Science").

This guide covers:
- What a profile contains
- Creating and managing profiles via CLI and webapp
- Importing and exporting profiles
- Profile storage (file-based vs. database)

---

## What's in a Profile

A profile is a JSON structure with these sections:

```json
{
  "basics": {
    "name": "Jane Doe",
    "headline": "Senior Software Engineer",
    "email": "jane@example.com",
    "phone": "555-0123",
    "location": "San Francisco, CA",
    "website": { "url": "https://janedoe.dev" }
  },
  "work": [
    {
      "company": "Acme Corp",
      "position": "Senior Engineer",
      "location": "San Francisco, CA",
      "startDate": "2020-01",
      "endDate": "",
      "highlights": ["Led team of 8 engineers", "Reduced latency by 40%"]
    }
  ],
  "education": [...],
  "skills": [...],
  "awards": [...],
  "certificates": [...],
  "projects": [...],
  "preferences": {
    "resume_style": "professional",
    "tone": "confident"
  },
  "narrative": {
    "career_summary": "10+ years building scalable systems..."
  }
}
```

The `profile_data` stored in the database uses this exact same structure — no schema change needed when migrating from files.

---

## Profile Storage

### File-based (default, backward compatible)

Without auth enabled, profiles are loaded from JSON files:

```
~/.config/fast-app/profile.json        # Default profile
./profile.json                          # Current directory (lowest precedence)
```

This is how Fast-App works today. No changes.

### Database-backed (with auth)

When auth is enabled, profiles are stored per-user in SQLite:

```sql
CREATE TABLE userprofile (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES user(id),
    name TEXT DEFAULT 'Default Profile',
    profile_data TEXT,  -- JSON string (same format as profile.json)
    is_default BOOLEAN DEFAULT FALSE,
    created_at DATETIME,
    updated_at DATETIME
);
```

**Loading priority:**
1. `--profile-id <id>` — Load specific profile from DB
2. Default profile in DB (where `is_default = TRUE`)
3. `--profile <path>` — Load from file path
4. `~/.config/fast-app/profile.json` — Load from XDG path

This ensures backward compatibility: if you don't use auth, profiles load from files as before.

---

## CLI Commands

### List profiles

```bash
# List all profiles for the current user
fast-app profile list

# Output:
# ID  Name              Default  Updated
# 1   General           Yes      2025-01-15
# 2   Engineering Lead  No       2025-01-20
```

### Show profile details

```bash
# Show the default profile
fast-app profile show

# Show a specific profile
fast-app profile show 2
```

### Create a profile

```bash
# Create an empty profile
fast-app profile create --name "Engineering Lead"

# Create from an existing JSON file
fast-app profile create --name "Data Science" --from-file ./profile_ds.json
```

### Import a profile

Importing reads a `profile.json` file and creates a database record:

```bash
# Import from a file
fast-app profile import ./profile.json

# Import with a custom name
fast-app profile import ./profile.json --name "Imported Profile"

# Import and set as default
fast-app profile import ./profile.json --default
```

### Export a profile

Exporting writes a database profile back to a JSON file:

```bash
# Export the default profile
fast-app profile export --output profile_export.json

# Export a specific profile
fast-app profile export 2 --output profile_ds.json
```

### Delete a profile

```bash
# Delete a profile by ID
fast-app profile delete 2

# You cannot delete the last default profile
# Set another profile as default first:
fast-app profile set-default 1
fast-app profile delete 2
```

### Set default profile

```bash
# Set profile 2 as the default
fast-app profile set-default 2
```

---

## Webapp Profile Management

In the webapp, profiles are managed under the "Profiles" section:

1. **Profile list**: Shows all profiles with name, default status, last updated
2. **Create**: Form to create a new profile (or import from JSON)
3. **Edit**: Edit profile fields directly in the browser
4. **Delete**: Remove a profile (cannot delete the last default)
5. **Set default**: Mark a profile as the default for resume generation

When generating a resume, the webapp uses the default profile unless a specific profile is selected.

---

## Migration from File-Based Profiles

If you're currently using `profile.json`, migrating to database profiles is simple:

```bash
# Step 1: Enable auth (set JWT secret and create account)
export FAST_APP_JWT_SECRET="your-secret"
fast-app auth signup --email you@example.com --password "password"

# Step 2: Import your existing profile
fast-app profile import ~/.config/fast-app/profile.json --default

# Step 3: Your profile is now in the database
fast-app profile list
```

The original `profile.json` file is **not modified**. It's kept as a backup. The database takes precedence once auth is enabled.

---

## Profile Schema Flexibility

The `profile_data` column is stored as a JSON string. This means:

- The profile structure can evolve without database migrations
- New fields can be added without schema changes
- The JSON structure is identical to the file-based `profile.json`
- All fields are optional — a minimal profile with just `basics.name` is valid

This design avoids the impedance mismatch between a rigid database schema and the flexible profile format that Reactive Resume expects.