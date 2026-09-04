# Design Specification: CTKM Multi-Store Task Monitoring Matrix

## 1. Overview & Problem Statement

### 1.1 Context
In the CTKM module, users access their assigned tasks through the **"Công việc của tôi"** menu (`action_ctkm_task_my` pointing to model `ctkm.task`).
Currently:
1. The default context is:
   ```python
   {'search_default_is_current_stage_task': 1, 'search_default_group_program_id': 1}
   ```
   This filters tasks to only the current stage while grouping by CTKM.
2. The user requirement is to have **only** the grouping by "CTKM" in default (`search_default_group_program_id: 1`), without filtering out other stages.
3. However, when all tasks are shown grouped by CTKM, users who manage multiple stores (e.g., ASMs, area managers, store supervisors) across multiple CTKMs face severe information overload:
   - They cannot see at a glance which stores are finished vs. pending for each CTKM.
   - They must open each individual task form and inspect store tabs to find their store's progress.

### 1.2 Objectives
1. Update `action_ctkm_task_my` to default solely to grouping by CTKM (`search_default_group_program_id: 1`).
2. Provide a collapsible, high-level **2D Monitoring Matrix panel** (`CtkmStoreProgressMatrix`) at the top of the "Công việc của tôi" list page:
   - **Rows**: Active CTKM programs.
   - **Columns**: Managed stores for the current user.
   - **Cells**: Current active step and color-coded status badge (`Hoàn thành`, `Đang làm`, `Chờ xác nhận`, `Chưa bắt đầu`).
   - **Interactivity**: Clicking a cell filters the task list below to that specific CTKM and stage, and provides a quick `[Mở công việc]` shortcut.
   - **Collapsible**: Users can collapse/expand the matrix panel with `[Thu gọn]` / `[Mở rộng]`; preference is saved in `localStorage`.
3. **UI Constraint**: No icons or emojis anywhere in the interface (text labels and CSS badge classes only).

---

## 2. Backend Architecture

### 2.1 RPC Method on `ctkm.task`
Add an `@api.model` method:
`ctkm.task.get_user_store_progress_matrix()`

#### Store Scoping Logic
1. Identify the current user's relevant stores:
   - From `hr.employee.managed_store_ids` ("Cửa hàng quản lí").
   - From `res.users.assigned_ma_bo_phan_ids` (LUG Permission "Mã bộ phận được xem").
   - From `hr.employee.ma_bo_phan_id` or `employee.store_id`.
   - If the user is an administrator or CTKM Manager (`group_ctkm_manager`) with no specific assigned stores, dynamically discover all distinct stores that have records across the active CTKM programs.
2. Output a deduplicated, sorted list of stores:
   ```python
   stores = [
       {'key': store_key, 'code': store_code, 'name': store_name},
       ...
   ]
   ```

#### Program and Cell Status Calculation
1. Fetch active programs where the user has tasks or store assignments:
   ```python
   domain = [
       ('program_id.state', 'not in', ['draft', 'cancel']),
       '|',
           ('user_ids', 'in', [self.env.uid]),
           ('store_verifier_ids.verifier_user_id', 'in', [self.env.uid])
   ]
   ```
2. For each active program and each store:
   - Inspect store-level lines across relevant stages:
     - Step 9 (In tem): `print_store_ids` (`done`, `store_key`).
     - Step 10 (Bàn giao/thu tem): `handover_store_ids` / `collect_store_ids`.
     - Step 11 & 12 (Nhận tem & Thay tem): `tem_tag_replace_ids` (`replaced_quantity >= total_quantity`).
     - Step 13 & 14 (Chụp ảnh & Kiểm tra ảnh): photo/check store lines.
     - Step 15 (Áp giá): `price_store_ids` (`price_applied`).
     - Step 16 (Hậu kiểm): `postcheck_store_ids` (`done`).
   - Identify the **current active step** for this store (the earliest stage with unfinished work).
   - If all stages for this store are done, status is `Hoàn thành` (`badge_class: success`).
   - Else, assign status based on that task's state:
     - `progress` $\rightarrow$ `Đang làm` (`badge_class: warning`)
     - `waiting_confirm` $\rightarrow$ `Chờ xác nhận` (`badge_class: info`)
     - `todo` $\rightarrow$ `Chưa bắt đầu` (`badge_class: secondary`)
   - Include the `task_id` corresponding to that step.

#### Payload Structure
```json
{
  "has_data": true,
  "stores": [
    { "key": "CH_NT", "code": "NT", "name": "CH Nguyễn Trãi" },
    { "key": "CH_CG", "code": "CG", "name": "CH Cầu Giấy" }
  ],
  "programs": [
    {
      "id": 101,
      "name": "CTKM Tết 2026",
      "code": "TB-01/2026",
      "cells": {
        "CH_NT": {
          "task_id": 452,
          "stage_seq": 12,
          "stage_name": "Thay tem Tag",
          "state": "progress",
          "state_label": "Đang làm",
          "badge_class": "warning"
        },
        "CH_CG": {
          "task_id": 453,
          "stage_seq": 13,
          "stage_name": "Chụp ảnh tem",
          "state": "waiting_confirm",
          "state_label": "Chờ xác nhận",
          "badge_class": "info"
        }
      }
    }
  ]
}
```

---

## 3. Frontend OWL Architecture

### 3.1 Custom List Controller: `ctkm_task_list_with_matrix`
- Extend Odoo's standard `ListController`:
  - Path: `custom_addons/ctkm_core/static/src/js/ctkm_task_list_matrix.js`
  - Template: `custom_addons/ctkm_core/static/src/xml/ctkm_task_list_matrix.xml`
  - Stylesheet: `custom_addons/ctkm_core/static/src/scss/ctkm_task_list_matrix.scss`
- Register in views registry:
  ```javascript
  registry.category("views").add("ctkm_task_list_with_matrix", {
      ...listView,
      Controller: CtkmTaskListMatrixController,
  });
  ```

### 3.2 OWL Component: `CtkmStoreProgressMatrix`
- Sub-component embedded in the list controller template immediately above the standard list renderer.
- **State**:
  - `collapsed`: Boolean, initialized from `localStorage.getItem('ctkm_matrix_collapsed') === 'true'`.
  - `loading`: Boolean, indicates active RPC fetch.
  - `data`: Stores the JSON payload from `get_user_store_progress_matrix()`.
  - `selectedCell`: Active cell for quick action popup.
- **Header Section**:
  - Title: `Tiến độ theo cửa hàng` (Plain text, no icons).
  - Summary count badges: e.g. `X Cửa hàng` • `Y CTKM`.
  - Button `[Làm mới]`: Triggers a silent reload of matrix data.
  - Button `[Thu gọn]` / `[Mở rộng]`: Toggles table visibility and updates `localStorage`.
- **Table Section**:
  - `table-responsive` wrapper with sticky column headers and sticky first column (CTKM Name).
  - Max height: `350px` with vertical scrolling.
  - Clickable cell badges with text labels.
- **Interactivity**:
  - On cell click:
    1. Triggers search model / domain filter on the list view below to filter for `program_id = program.id` (and optionally `id = cell.task_id`).
    2. Shows a lightweight popover or inline action `[Mở công việc]` to open the task form view directly via `actionService.doAction`.

---

## 4. View and Action Modifications

### 4.1 Action `action_ctkm_task_my`
In `custom_addons/ctkm_core/views/ctkm_task_views.xml`:
- Update context:
  ```xml
  <field name="context">{'search_default_group_program_id': 1}</field>
  ```

### 4.2 List View `view_ctkm_task_list`
In `custom_addons/ctkm_core/views/ctkm_task_views.xml`:
- Add `js_class="ctkm_task_list_with_matrix"`:
  ```xml
  <list string="Công việc của tôi" create="0" delete="0"
        class="o_ctkm_task_list" js_class="ctkm_task_list_with_matrix"
        default_order="checklist_line_id, id">
  ```

### 4.3 Manifest Assets
In `custom_addons/ctkm_core/__manifest__.py`:
- Add `ctkm_task_list_matrix.js`, `ctkm_task_list_matrix.xml`, and `ctkm_task_list_matrix.scss` to `web.assets_backend`.

---

## 5. Non-Functional Requirements & Constraints

1. **No Icons / No Emojis**:
   - Strictly avoid emojis (e.g. 📊, 🟢, 🔄) and icons (FontAwesome `fa-*`, SVG icons).
   - Use plain text labels and Bootstrap badges (`badge bg-success`, `badge bg-warning`, etc.).
2. **Performance**:
   - Single batch query to build the matrix data.
   - Matrix RPC does not block the list view rendering.
3. **Empty State**:
   - If user has no assigned stores, display a clean text message: `Chưa có dữ liệu cửa hàng cần theo dõi.`
4. **Backward Compatibility**:
   - Existing filters (`Bước hiện tại`, `Của tôi`, `Chờ tôi xác nhận`) in `view_ctkm_task_search` remain intact for manual use.

---

## 6. Testing & Verification

1. **Backend Unit Test**:
   - Test `get_user_store_progress_matrix()` with mock users having 1 store, multiple stores, and manager permissions.
   - Verify step resolution for completed, in-progress, and unstarted store stages.
2. **Frontend UI Verification**:
   - Navigate to "Công việc của tôi" and verify that tasks are grouped solely by CTKM by default.
   - Verify that the "Tiến độ theo cửa hàng" matrix renders with correct store columns and CTKM rows.
   - Verify that toggling `[Thu gọn]` / `[Mở rộng]` collapses the panel and persists on page reload.
   - Verify clicking a cell filters the list view and allows direct navigation to the task form.
   - Verify no icons or emojis appear in the rendered HTML.
