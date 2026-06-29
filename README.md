# 💬 Slack Follow-Up Bot

Automated follow-ups for people who haven't filled out forms/surveys. Sends Slack DMs to remind them!

---

## 🚀 Quick Start Guide

### Step 1: Go to GitHub Actions
```
https://github.com/YOUR-USERNAME/slackautomation/actions
```

### Step 2: Choose Your Workflow

You have **2 workflows** to choose from:

#### Option A: **"Follow-up bot"** (Automated Messages)
- For sending follow-up messages via command line
- Can run manually or on a schedule

#### Option B: **"Launch Web UI"** (Interactive Interface)
- Launches a beautiful web interface
- Get a temporary public URL
- Visual preview of who will get messages

---

## 📋 How to Use "Follow-up bot" Workflow

### 1. Click "Follow-up bot" → "Run workflow"

### 2. Fill in the 5 fields:

| Field | What to Enter | Example |
|-------|---------------|---------|
| **1️⃣ Employee list URL** | Your Google Sheet with all employees (published as CSV) | `https://docs.google.com/.../pub?output=csv` |
| **2️⃣ Form responses URL** | Your Google Sheet with people who responded (published as CSV) | `https://docs.google.com/.../pub?output=csv` |
| **3️⃣ Custom message** | The message to send (use `{name}` for first name) | `Hi {name}! Please fill the form...` |
| **4️⃣ Actually send messages** | ✅ CHECK to send / ❌ UNCHECK to preview | |
| **5️⃣ Force send to everyone** | ⚠️ **KEEP UNCHECKED** for normal use | |

### 3. Click "Run workflow"

---

## ✅ **IMPORTANT: Checkbox Settings**

### 🎯 Normal Use (Recommended)
**Goal:** Send messages ONLY to people who haven't responded

```
4️⃣ Actually send messages?        ✅ CHECKED
5️⃣ Force send to everyone?        ❌ UNCHECKED
```

**Result:** Bot compares employee list vs responses, sends ONLY to non-responders

---

### 👀 Preview Mode (Safe Testing)
**Goal:** See who would get messages WITHOUT actually sending

```
4️⃣ Actually send messages?        ❌ UNCHECKED
5️⃣ Force send to everyone?        ❌ UNCHECKED
```

**Result:** Bot shows you who would get messages but doesn't send anything

---

### 🧪 Test Mode (For Testing Only!)
**Goal:** Send to EVERYONE including people who already responded

```
4️⃣ Actually send messages?        ✅ CHECKED
5️⃣ Force send to everyone?        ✅ CHECKED
```

**Result:** Bot sends to ALL employees, ignoring who has responded

⚠️ **WARNING:** Only use this for testing with yourself! It will spam everyone.

---

## 📊 How It Works

### The Logic:
```
1. Bot loads Employee List (everyone who should respond)
2. Bot loads Form Responses (people who already responded)
3. Bot compares: Employee List - Responses = Pending people
4. Bot sends messages to Pending people only
5. Bot remembers who it contacted (won't spam the same person)
```

### Example:

**Employee List:**
```csv
Name,Email
John,john@company.com
Jane,jane@company.com
Bob,bob@company.com
Alice,alice@company.com
```

**Form Responses:**
```csv
Name,Email
Jane,jane@company.com
Bob,bob@company.com
```

**Who Gets Messages?**
- ❌ Jane → No message (already responded)
- ❌ Bob → No message (already responded)
- ✅ John → Gets follow-up message
- ✅ Alice → Gets follow-up message

**Result:** Only John and Alice get messages!

---

## 🔧 Setup Requirements

### 1. Google Sheets Must Be Published

Both sheets must be **published to web as CSV**:

1. Open your Google Sheet
2. File → Share → Publish to web
3. Choose "Entire Document" or specific sheet
4. Format: **CSV**
5. Click "Publish"
6. Copy the URL (must end with `output=csv`)

**Correct URL format:**
```
https://docs.google.com/spreadsheets/d/e/2PACX-.../pub?output=csv
```

### 2. GitHub Secrets (Already Set)

Your repository already has these secrets configured:
- `SLACK_BOT_TOKEN` - Your Slack user token
- `SLACK_OWNER_ID` - Your Slack user ID
- `EMPLOYEES_CSV_URL` - Default employee list URL
- `SHEET_CSV_URL` - Default responses URL

---

## 🎨 Launch Web UI Workflow

Want a beautiful visual interface instead?

### 1. Click "Launch Web UI" → "Run workflow"
### 2. Choose session duration (30, 60, 120, or 180 minutes)
### 3. Wait 1-2 minutes for it to start
### 4. Check the logs for your public URL
### 5. Open the URL in your browser
### 6. Upload files or paste Google Sheet URLs
### 7. Preview who will get messages
### 8. Click "Send" button

The session will stay alive for your chosen duration, then automatically shut down.

---

## ❓ FAQ

**Q: Why are people who already responded still getting messages?**
A: You probably checked the "Force send to everyone" checkbox. Keep it UNCHECKED for normal use!

**Q: How do I test without sending real messages?**
A: Uncheck BOTH checkboxes. Bot will run in preview mode and show you who would get messages.

**Q: Can I customize the message?**
A: Yes! Edit field 3️⃣. Use `{name}` to insert the person's first name.

**Q: How often can I run this?**
A: As often as you want! Bot remembers who it contacted and waits 24 hours before sending another nudge.

**Q: What if someone responds after I send a message?**
A: Next time you run the bot (with normal settings), it will detect they responded and won't send another message.

**Q: Can I send to just one specific person?**
A: Yes! Create an employee CSV with just that one person and use force mode.

---

## 📝 File Formats

### Employee List CSV:
```csv
Name,Email,Message
John Doe,john@company.com,
Jane Smith,jane@company.com,Hi {name}! Custom message here
```

**Columns:**
- `Name` (required) - Full name
- `Email` (required) - Email address
- `Message` (optional) - Custom message for this person

### Responses CSV:
```csv
Timestamp,Name,Email
2026-06-29 10:30:00,Jane Smith,jane@company.com
2026-06-29 11:45:00,Bob Johnson,bob@company.com
```

**Columns:**
- `Name` or `Email` (at least one required)
- Other columns are ignored

---

## 🛡️ Safety Features

✅ **Anti-spam protection** - Won't send to same person within 24 hours
✅ **Max rounds** - Stops after 3 nudges per person
✅ **Preview mode** - Test before sending
✅ **State tracking** - Remembers who was contacted
✅ **Responder detection** - Automatically excludes people who responded

---

## 🎯 Best Practices

1. **Always preview first** - Run with both checkboxes unchecked to see who would get messages
2. **Use normal mode** - Keep "Force send" unchecked for production use
3. **Check responses regularly** - Run the workflow after people have had time to respond
4. **Customize messages** - Personalized messages get better response rates
5. **Test with yourself** - Add yourself to employee list with force mode to test

---

## 📞 Support

Having issues? Check:
1. Google Sheets are published as CSV (URL ends with `output=csv`)
2. Slack token has correct permissions
3. You're using the correct checkbox settings
4. Preview mode works before trying to send

---

Made with ❤️ by Kiro AI
