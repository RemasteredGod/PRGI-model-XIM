# PRGI Batch Upload & Admin Review System

## 🎯 New Features Added

### 1. **Batch Upload Page** (`batch.html`)

Upload multiple titles at once and get comprehensive analytics.

**Features:**

- ✅ Drag & drop file upload
- ✅ Support for CSV, XLS, XLSX, TXT formats
- ✅ Real-time processing with progress indicator
- ✅ 6 Interactive visualization charts:
  - **Rule Violation Distribution** (Histogram with colors)
  - **Prefix Usage Distribution** (Leaderboard)
  - **Statewise Rejection Rate** (Pie chart)
  - **Unique vs Duplicate Ratio** (Doughnut chart)
  - **Rejection Confidence Levels** (Gradient histogram)
  - **Language-Based Similarity** (Radar chart)
- ✅ "Send Request to Admin" button for batch approval

### 2. **Admin Login System**

Secure authentication for admin access.

**Default Credentials:**

- Username: `admin`
- Password: `admin123`

### 3. **Acceptance Ratio Configuration**

Admin can configure the acceptance threshold (0-100%).

**Features:**

- ✅ Interactive slider control
- ✅ Saved to database
- ✅ Affects approval decisions

### 4. **Excel-Like Review Page** (`admin-review.html`)

Comprehensive spreadsheet-style interface for reviewing titles.

**Features:**

- ✅ Excel-like table with row selection
- ✅ Multi-select with checkboxes
- ✅ Filter by status (All/Pending/Approved)
- ✅ Bulk operations
- ✅ "Move to Original DB" action for approved titles
- ✅ Fixed action bar showing selection count

### 5. **Two Database System**

- **temp.db** (Temp2 Database) - Stores batch uploads and admin-approved titles
- **Original DB** (titles table) - Final database for production titles
- Admin manually reviews and moves titles from temp2 → original

---

## 📁 File Structure

```
frontend/
├── index.html           # Main page (with Batch Upload link added)
├── admin.html           # Admin dashboard (with Excel Review link)
├── batch.html           # 🆕 Batch upload with analytics
└── admin-review.html    # 🆕 Excel-like review interface

backend/
├── main.py              # Updated with batch & auth endpoints
├── database.py          # Updated with new tables
├── requirements.txt     # Updated with new dependencies
└── models/schemas.py    # Updated with new models
```

---

## 🔧 Setup Instructions

### 1. Install New Dependencies

```bash
cd backend
pip install -r requirements.txt
```

New packages added:

- `openpyxl` - Excel file support
- `xlrd` - XLS file reading
- `python-jose[cryptography]` - JWT tokens
- `passlib[bcrypt]` - Password hashing

### 2. Start Backend

```bash
uvicorn backend.main:app --reload
```

The database will automatically create new tables:

- `batch_uploads`
- `batch_results`
- `admin_users` (with default admin user)
- `admin_config` (with default acceptance ratio)

### 3. Access Pages

**Main Application:**

- http://localhost:8000/frontend/index.html
- New "Batch Upload" link in navigation

**Batch Upload Page:**

- http://localhost:8000/frontend/batch.html
- Upload CSV/XLS/XLSX/TXT files
- View analytics and send to admin

**Admin Dashboard:**

- http://localhost:8000/frontend/admin.html
- Manage individual requests
- "Excel Review →" button to access review page

**Excel Review Page:**

- http://localhost:8000/frontend/admin-review.html
- Login required (admin/admin123)
- Configure acceptance ratio
- Review and approve titles in bulk

---

## 🎨 Color Scheme

All visualizations use ambient colors:

- 🔴 Red (`#b91c1c`) - Violations, Rejections
- 🟠 Orange (`#f97316`) - Phonetic issues
- 🟡 Yellow (`#d97706`) - Warnings
- 🟢 Green (`#16a34a`) - Approved, Unique
- 🔵 Blue (`#3b82f6`) - Information
- 🟣 Purple (`#9333ea`) - Combination issues
- 🩷 Pink (`#ec4899`) - Language conflicts

---

## 📊 API Endpoints Added

### Batch Processing

```
POST   /api/batch/upload                    # Upload batch file
GET    /api/batch/{batch_id}/results        # Get batch results
GET    /api/batch/{batch_id}/analytics      # Get analytics
POST   /api/batch/{batch_id}/approve        # Approve specific titles
POST   /api/batch/{batch_id}/request-approval  # Send batch to admin
```

### Admin Authentication & Config

```
POST   /api/admin/login                     # Admin login
GET    /api/admin/config/acceptance-ratio   # Get ratio
POST   /api/admin/config/acceptance-ratio   # Set ratio
```

---

## 🔄 Workflow

### User Workflow:

1. **Single Title:** Use main page validator → Request approval if rejected
2. **Batch Upload:** Go to Batch Upload page → Upload file → View analytics → Send to admin

### Admin Workflow:

1. **Login:** Access admin pages (username: admin, password: admin123)
2. **Configure:** Set acceptance ratio threshold
3. **Review Dashboard:** See pending requests in admin.html
4. **Approve/Reject:** Individual requests in dashboard
5. **Bulk Review:** Go to Excel Review page
6. **Select & Approve:** Select multiple titles → Move to Original DB

### Database Flow:

```
User Upload
    ↓
Temp2 Database (batch_results / approval_requests)
    ↓
Admin Review (admin-review.html)
    ↓
Manual Selection & Approval
    ↓
Original Database (titles table)
```

---

## 🎯 Key Features Implemented

✅ Drag & drop batch file upload  
✅ Support for CSV, Excel, TXT formats  
✅ 6 interactive charts with ambient colors  
✅ Admin login with bcrypt password hashing  
✅ Configurable acceptance ratio (0-100%)  
✅ Excel-like spreadsheet interface  
✅ Multi-select with bulk operations  
✅ Two-database system (temp2 → original)  
✅ Request approval workflow  
✅ Real-time progress indicators  
✅ Responsive dark theme UI

---

## 🔐 Security Notes

- Passwords are hashed using bcrypt
- Default admin credentials should be changed in production
- Consider adding JWT tokens for session management
- Add HTTPS in production environment

---

## 📝 Sample File Formats

### CSV Format:

```csv
title,language,state
The Times,English,Maharashtra
Dainik Jagran,Hindi,Uttar Pradesh
```

### TXT Format (one title per line):

```
The Hindu
Indian Express
Times of India
```

### Excel Format:

Any column named: `title`, `Title`, `TITLE`, `name`, or first column will be used.

---

## 🚀 Next Steps

1. Test batch upload with sample files
2. Review analytics visualizations
3. Configure acceptance ratio based on requirements
4. Use Excel review page for bulk approvals
5. Monitor temp2 database growth
6. Set up scheduled tasks to move approved titles

---

## 💡 Tips

- Use **Batch Upload** for processing multiple titles efficiently
- Set **acceptance ratio** based on your quality standards
- Use **Excel Review** for final quality control before moving to production
- Regular backups of both temp2 and original databases recommended
- Monitor analytics to identify common rejection patterns

---

## 🎉 Ready to Use!

All features are now live and ready to test. Start your backend server and access the pages!
