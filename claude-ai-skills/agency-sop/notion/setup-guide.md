# Notion Setup Guide for AEO Agency Workflow

This guide walks you through setting up Notion to work with your AEO Agency SOP and Claude skill.

---

## Step 1: Create Your Notion Account

1. Go to [notion.so](https://notion.so)
2. Sign up for a free account (free for up to 2 people)
3. Create a new workspace named after your agency
4. Invite your partner via email

---

## Step 2: Create the Job Tracker Database

### 2.1 Create a New Database
1. Click **+ New page** in the sidebar
2. Select **Table** as the database type
3. Name it **Job Tracker**

### 2.2 Add Required Properties

Delete any default columns and add these:

| Property Name | Type | Configuration |
|---------------|------|---------------|
| **Job Name** | Title | (default title column) |
| **Client** | Select | Add clients as you onboard them |
| **Status** | Select | Add all 10 stages (see below) |
| **Owner** | Person | Enable "Notify users when assigned" |
| **Priority** | Select | High, Medium, Low |
| **Due Date** | Date | Include time if needed |
| **Value** | Number | Format as currency (optional) |
| **Notes** | Text | For running updates |
| **Last Updated** | Last Edited Time | Automatic |

### 2.3 Configure Status Options

Add these status options in order:
1. Lead
2. Discovery
3. Quoted
4. Approved
5. Research
6. Drafting
7. Review
8. Revisions
9. Publishing
10. Complete

**Tip:** Use colours to visually group stages:
- **Blue** for sales (Lead, Discovery, Quoted)
- **Yellow** for setup (Approved)
- **Green** for production (Research, Drafting, Review, Revisions)
- **Purple** for delivery (Publishing, Complete)

---

## Step 3: Create Database Views

### 3.1 Kanban View (Main Working View)
1. Click **+ Add view** → **Board**
2. Name it "Pipeline"
3. Group by: **Status**
4. This becomes your daily working view

### 3.2 My Jobs View
1. Click **+ Add view** → **Table**
2. Name it "My Jobs"
3. Add filter: **Owner** contains **[your name]**
4. Each partner creates their own filtered view

### 3.3 Calendar View
1. Click **+ Add view** → **Calendar**
2. Name it "Deadlines"
3. Date property: **Due Date**
4. Use for deadline tracking

### 3.4 All Jobs Table
1. Keep the original table view
2. Rename it "All Jobs"
3. Use for detailed review and reporting

---

## Step 4: Connect Claude (via Notion MCP)

### 4.1 Enable the Connector
1. In Claude desktop app, go to **Settings** → **Connectors**
2. Find **Notion** in the connector list
3. Click **Connect** and authorize access to your workspace

### 4.2 Grant Access to Job Tracker
1. In Notion, open your Job Tracker database
2. Click **Share** → **Invite**
3. Make sure the integration has access

### 4.3 Test the Connection
1. Start a new Claude conversation
2. Say: "Check my Notion job tracker"
3. Claude should be able to read your database

---

## Step 5: Create a Clients Database

Create a database to manage client information:

1. Click **+ New page** in the sidebar
2. Select **Table** as the database type
3. Name it **Clients**

| Property | Type | Notes |
|----------|------|-------|
| Client Name | Title | Company name |
| Contact | Text | Primary contact name |
| Email | Email | Contact email |
| Status | Select | Active, Paused, Completed |
| Preferences | Text | Client-specific style notes (from feedback loop) |
| Notes | Text | General notes |

Then update **Job Tracker**:
1. Change the **Client** property from Select to **Relation**
2. Link it to the Clients database

---

## Step 6: Create the Content Library

The Content Library tracks all published content per client. This enables:
- Internal linking suggestions in future articles
- Tracking what's been produced
- Linking completed jobs to their outputs

### 6.1 Create the Database

1. Click **+ New page** in the sidebar
2. Select **Table** as the database type
3. Name it **Content Library**

### 6.2 Add Properties

| Property | Type | Configuration |
|----------|------|---------------|
| **Title** | Title | Article title |
| **Client** | Relation | Link to Clients database |
| **URL** | URL | Published location |
| **Primary Keyword** | Text | Target keyword |
| **Entities** | Multi-select | Entities covered (add as you go) |
| **Content Type** | Select | Comparison, Listicle, Guide, etc. |
| **Published Date** | Date | When it went live |
| **Status** | Select | Draft, Published, Archived |
| **Related Job** | Relation | Link to Job Tracker |

### 6.3 Create Views

1. **All Content** — Default table view
2. **By Client** — Create a filtered view for each active client
3. **Recent** — Filter: Published Date is within last 30 days

### 6.4 Linking to Job Tracker

When a job reaches **Complete** status:
1. Create an entry in Content Library
2. Fill in: Title, URL, Keyword, Entities, Content Type
3. Set the **Related Job** relation to link back to the job

This creates a two-way link:
- From Job Tracker, see what content was produced
- From Content Library, see which job created each piece

### 6.5 Using for Internal Links

When working on new content for a client:
1. Query Content Library filtered by that client
2. Identify relevant existing articles
3. Mark internal link opportunities in the draft

---

## Step 8: Set Up Templates

### New Job Template
1. In Job Tracker, click the dropdown arrow next to **New**
2. Click **+ New template**
3. Name it "New Client Job"
4. Pre-fill:
   - Status: Lead
   - Priority: Medium
   - Notes: "Source: [where did this lead come from?]"

### Use templates when creating new jobs for consistency.

---

## Quick Tips

- **Pin your Pipeline view** for easy access
- **Use keyboard shortcuts**: Press `N` to create new entry
- **Enable notifications** for assigned jobs
- **Review the database weekly** for stale items

---

## Connecting with the Claude Skill

Once Notion is set up and connected:

1. Install the `aeo-agency-workflow.skill` file in Claude
2. When you say "new project" or "check my pipeline", Claude will:
   - Read your current jobs from Notion
   - Guide you through the correct workflow
   - Help update status and ownership
   - Prevent overlap by checking who owns what

---

## Troubleshooting

**Claude can't see my database:**
- Check that the Notion integration has access to the specific page
- Try re-authorizing the connection

**Status options don't match:**
- Ensure you've added all 10 stages exactly as listed
- The skill expects these specific status names

**Permissions issues:**
- Both partners should be Admins of the workspace
- Guests have limited editing capabilities

---

## Next Steps

1. ✅ Create Notion account and workspace
2. ✅ Set up Clients database
3. ✅ Set up Job Tracker database (with relation to Clients)
4. ✅ Set up Content Library database
5. ✅ Create views (Pipeline, My Jobs, Deadlines, By Client)
6. ✅ Connect Claude via Notion MCP
7. ✅ Install the aeo-agency-workflow.skill
8. ✅ Create your first test job

You're ready to go! Load the skill and say "new project" to get started.
