# TUI Design Document: Knowledge Base Explorer

## Overview

The Knowledge Base TUI (Terminal User Interface) is an interactive tool for browsing, searching, and editing the SQLite knowledge base. Built with **Textual** (Python TUI framework), it provides a split-view interface with navigation on the left, facts table in the center, and a detail/edit panel.

---

## CLI Commands

### Command Overview

```bash
fast-app profile [SUBCOMMAND] [OPTIONS]
```

### Available Commands

| Command | Alias | Description | Opens |
|---------|-------|-------------|-------|
| `fast-app profile` | `fast-app profile edit` | Open main explorer view | Main TUI (all facts view) |
| `fast-app profile show` | | Open statistics dashboard | Show TUI (dashboard view) |
| `fast-app profile stale` | | Open stale facts view | Stale TUI (filtered to low-confidence facts) |
| `fast-app profile dump` | `--output FILE` | Export KB to JSON (non-interactive) | Stdout or file |
| `fast-app profile load FILE` | | Import KB from JSON (non-interactive) | N/A |

### Command Details

#### `fast-app profile` (Default: Main Explorer)

**Purpose**: Browse and edit all facts in the knowledge base.

**Behavior**:
- Opens interactive TUI
- Shows all facts by default
- Left sidebar shows categories
- Right panel shows fact table
- Bottom shows fact details/edits

**Arguments**: None

**Options**: None

---

#### `fast-app profile edit` (Alias for `profile`)

**Purpose**: Same as `fast-app profile` - open main explorer.

---

#### `fast-app profile show`

**Purpose**: View statistics and overview.

**Behavior**:
- Opens interactive TUI
- Shows dashboard with:
  - Total facts count
  - Facts by type breakdown
  - Average confidence
  - Generations count
  - Success/failure ratio
  - Facts needing refresh
- "Quick Actions" to jump to specific views

---

#### `fast-app profile stale`

**Purpose**: Review facts that need confirmation.

**Behavior**:
- Opens interactive TUI
- Pre-filtered to facts with confidence < 0.6
- Sorted by confidence (lowest first)
- Color-coded urgency
- Actions: Confirm, Edit, Delete

---

#### `fast-app profile dump --output FILE`

**Purpose**: Export knowledge base to JSON.

**Behavior**:
- Non-interactive command
- Prints JSON to stdout if no `--output`
- Writes to file if `--output` specified
- Includes all facts, generations, patterns, metadata

**Options**:
- `--output, -o PATH` - File path to write JSON

---

#### `fast-app profile load FILE`

**Purpose**: Import knowledge base from JSON backup.

**Behavior**:
- Non-interactive command
- Prompts for confirmation before loading
- Replaces all existing data
- Shows count of imported records

---

## View 1: Main Explorer (default)

**Screen Name**: `MainScreen`

**Command**: `fast-app profile` or `fast-app profile edit`

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Knowledge Base Explorer                   [F1 Help] [/ Search] [Q Quit] [Tab] │
├────────────────────┬─────────────────────────────────────────────────────────┤
│                    │                                                           │
│  Categories        │  Facts (147 total)                        [Search...] │
│                    │  ┌─────────────────────────────────────────────────────┐│
│  ► All Facts (147) │  │ Type        Text                        Conf Age  ││
│  ▸ Skills (32)     │  ├─────────────────────────────────────────────────────┤│
│  ▸ Experience (45) │  │ skill       5 years Python experience   95%  2d   ││
│  ▸ Achievement (38)│  │ skill       3 years JavaScript          90%  5d   ││
│  ▸ Preference (21) │  │ experience  Worked at Google 2020-2023   100% 1d   ││
│  ▸ General (11)    │  │ achievement Led team of 5 developers    87% 14d  ││
│                    │  │ ...                                              ││
│ ────────────────── │  └─────────────────────────────────────────────────────┘│
│                    │                                                           │
│  Generations       │  ┌─────────────────────────────────────────────────────┐│
│    Recent (12)      │  │  Selected: 5 years Python experience               ││
│    Success (8)      │  │  ──────────────────────────────────────────────────││
│    Failed (4)       │  │  ID:        a1b2c3d4-e5f6-...                     ││
│                    │  │  Type:      skill                                 ││
│                    │  │  Confidence: 95%                                  ││
│                    │  │  Source:    qa                                     ││
│                    │  │  Age:       2 days                                 ││
│                    │  │                                                     ││
│                    │  │  [Edit]  [Confirm]  [Delete]  [History]            ││
│                    │  └─────────────────────────────────────────────────────┘│
│                    │                                                           │
├────────────────────┴─────────────────────────────────────────────────────────┤
│  ↑/↓ Navigate │ Enter Edit │ N New │ D Delete │ / Search │ ? Sidebar │ Q  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Components

#### Left Sidebar (Categories)

- Tree widget with collapsible nodes
- Shows categories with counts
- Shows generations with counts
- Dynamic "Search Results" node when searching

#### Center DataTable (Facts Table)

- Sortable, filterable table
- Columns: Type, Text, Confidence, Age
- Color-coded: Green (≥80%), Yellow (50-79%), Red (<50%)
- Alternating row backgrounds

#### Bottom Detail Panel

- Shows selected fact details
- Action buttons: Edit, Confirm, Delete, History

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑/k` | Move up |
| `↓/j` | Move down |
| `←/h` | Previous category |
| `→/l` | Next category |
| `Enter` | Edit fact |
| `N` | New fact |
| `D` | Delete fact |
| `/` | Search |
| `?` | Toggle sidebar |
| `C` | Confirm fact |
| `R` | Refresh |
| `F` | Filter |
| `S` | Sort |
| `F1` | Help |
| `Q/Esc` | Quit |

---

## View 2: Statistics Dashboard (show)

**Screen Name**: `ShowScreen`

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Statistics Dashboard                    [F1 Help] [Q Quit] [B Back]         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Total Facts: 147       Average Confidence: 89%      Needing Refresh: 3│ │
│  │  Total Generations: 12  Success Rate: 67%          Average Rating: 4.2│ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  Facts by Type:                      Facts by Source:                       │
│  skill        32  ████████           qa           89  ████████████        │
│  experience   45  ███████████       profile      45  ██████████            │
│  achievement  38  █████████        imported     13  ███                   │
│  preference   21  █████            inferred      0                          │
│  general     11  ███                                             │
│                                                                              │
│  Facts Needing Refresh (3):                                                │
│  • "I prefer dark mode" - 45 days old, confidence: 41%                     │
│  • "Worked with React" - 60 days old, confidence: 38%                     │
│  • "Looking for remote work" - 90 days old, confidence: 29%               │
│                                                                              │
│  [View All Facts]  [View Stale Facts]  [Search]  [New Fact]                │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  [B] Back │ [Q] Quit                                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## View 3: Stale Facts (stale)

**Screen Name**: `StaleScreen`

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Stale Facts - Needing Confirmation      [F1 Help] [Q Quit] [B Back]       │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Facts below 60% confidence need your review.                               │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │ ✓ │ Type        │ Text                            │ Conf │ Age │ Urgency │ │
│  ├──────────────────────────────────────────────────────────────────────────┤ │
│  │ □ │ preference  │ Looking for remote work         │ 29%  │ 90d │ High   │ │
│  │ □ │ skill       │ Worked with React                │ 38%  │ 60d │ High   │ │
│  │ □ │ preference  │ I prefer dark mode               │ 41%  │ 45d │ Medium │ │
│  │ □ │ skill       │ Some SQL experience              │ 52%  │ 35d │ Medium │ │
│  │ ...            │                                  │      │     │        │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  Selected: "Looking for remote work"                                        │
│  You said this 90 days ago. Is this still accurate?                          │
│                                                                              │
│  [Confirm Still Accurate]  [Edit & Confirm]  [Mark as Wrong]  [Skip]      │
│                                                                              │
│  [Confirm Selected]  [Confirm All]  [Skip All]                              │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  ↑/↓ Navigate │ Space Select │ Enter Confirm │ B Back │ Q Quit              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## View 4: Inline Edit Mode

**Trigger**: Press `Enter` on selected fact

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Editing Fact                           [Ctrl+S Save] [Esc Cancel]          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Text:    [5 years Python experience_______________________________________] │
│                                                                              │
│  Type:    [skill] ▼                                                          │
│                                                                              │
│  Confidence: [0.95]                                                          │
│                                                                              │
│  Job URL:  [https://company.com/job/123___________________________________] │
│                                                                              │
│  [Ctrl+S Save]  [Esc Cancel]                                                │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  Tab Next Field │ Shift+Tab Previous │ Ctrl+S Save │ Esc Cancel             │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## View 5: New Fact Modal

**Trigger**: Press `N` in MainScreen

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  New Fact                               [Create] [Cancel]                    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Text:    [_______________________________________________________________] │
│                                                                              │
│  Type:    [general] ▼                                                       │
│                                                                              │
│  Confidence: [0.80]                                                          │
│                                                                              │
│  Source:  [qa] ▼                                                            │
│                                                                              │
│  [Create]  [Cancel]                                                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## View 6: Delete Confirmation Modal

**Trigger**: Press `D` on selected fact

### Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Confirm Delete                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Are you sure you want to delete this fact?                                  │
│                                                                              │
│  "5 years Python experience"                                                │
│  Type: skill | Confidence: 95%                                              │
│                                                                              │
│  This cannot be undone.                                                      │
│                                                                              │
│  [Delete]  [Cancel]                                                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## View Transitions

```
CLI Commands:
  fast-app profile  ──────────────► MainScreen (Browse)
  fast-app show      ──────────────► ShowScreen (Stats)
  fast-app stale     ──────────────► StaleScreen (Review)

MainScreen:
  Enter  ─────────────────────────► EditMode (Inline Edit)
  N      ─────────────────────────► NewFactModal
  D      ─────────────────────────► DeleteModal
  ?      ─────────────────────────► Toggle Sidebar
  F1     ─────────────────────────► HelpModal

ShowScreen:
  B      ─────────────────────────► MainScreen
  V      ─────────────────────────► MainScreen (View All)
  S      ─────────────────────────► StaleScreen

StaleScreen:
  B      ─────────────────────────► MainScreen
  Enter  ─────────────────────────► Confirm fact
  D      ─────────────────────────► DeleteModal

Global:
  F1     ─────────────────────────► HelpModal (overlay)
  Q/Esc  ─────────────────────────► Quit
```

---

## Keyboard Shortcuts Summary

### MainScreen

| Key | Action |
|-----|--------|
| `↑/k` | Move selection up |
| `↓/j` | Move selection down |
| `←/h` | Previous category |
| `→/l` | Next category |
| `Enter` | Edit selected fact |
| `N` | New fact |
| `D` | Delete fact |
| `/` | Search |
| `?` | Toggle sidebar |
| `C` | Confirm fact |
| `R` | Refresh |
| `F1` | Help |
| `Q/Esc` | Quit |

### Edit Mode

| Key | Action |
|-----|--------|
| `Tab` | Next field |
| `Shift+Tab` | Previous field |
| `Ctrl+S` | Save |
| `Esc` | Cancel |

### StaleScreen

| Key | Action |
|-----|--------|
| `↑/↓` | Navigate |
| `Space` | Toggle selection |
| `Enter` | Confirm fact |
| `E` | Edit & confirm |
| `W` | Mark as wrong |
| `S` | Skip |
| `C` | Confirm selected |
| `A` | Confirm all |
| `B` | Back to main |
| `Q/Esc` | Quit |

---

## Implementation Files

```
src/fast_app/tui/
├── __init__.py              # Public API
├── app.py                   # Main Textual App class
├── screens/
│   ├── __init__.py
│   ├── main.py             # MainScreen (browse)
│   ├── show.py             # ShowScreen (stats)
│   └── stale.py            # StaleScreen (review)
├── widgets/
│   ├── __init__.py
│   ├── sidebar.py          # Sidebar navigation
│   ├── fact_table.py       # Facts table
│   └── detail_panel.py     # Fact details
└── styles.css              # Textual CSS
```