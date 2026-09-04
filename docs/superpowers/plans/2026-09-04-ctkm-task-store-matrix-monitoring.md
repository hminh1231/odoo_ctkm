# CTKM Multi-Store Task Monitoring Matrix Implementation Plan

> **User-Facing Summary**: Updates the "Công việc của tôi" page so default filters group solely by CTKM, and integrates a collapsible 2D monitoring matrix (CTKMs × Stores) at the top of the task list displaying each store's current active step and status badge without any icons.
> **Proposed Changes**:
> - Update `action_ctkm_task_my` default context to `{'search_default_group_program_id': 1}`.
> - Implement `ctkm.task.get_user_store_progress_matrix()` to calculate store-level active steps and status badges for the current user's stores.
> - Create an OWL component `CtkmStoreProgressMatrix` and custom ListController `ctkm_task_list_with_matrix`.
> - Style the matrix with sticky headers/columns, text-only badges, and collapsible state saved in `localStorage`.
> - Connect `view_ctkm_task_list` with `js_class="ctkm_task_list_with_matrix"`, update assets in manifest, and bump module version to 4.31.
> **Verification Plan**:
> - Automated test running `get_user_store_progress_matrix()` verifying correct store discovery and status computation.
> - Verification of XML views and action context.
> - JS/SCSS asset registration and syntax validation.
> - Verification that zero icons or emojis appear in templates or UI text.

---

### Task 1: Update Default Search Filter & Action Context in Views

- **Files to modify**:
  - `custom_addons/ctkm_core/views/ctkm_task_views.xml`
- **Action**:
  1. In `action_ctkm_task_my` (around line 724), replace:
     ```xml
     <field name="context">{'search_default_is_current_stage_task': 1,
         'search_default_group_program_id': 1}</field>
     ```
     with:
     ```xml
     <field name="context">{'search_default_group_program_id': 1}</field>
     ```
  2. In `view_ctkm_task_list` (around line 9), update `default_order="checklist_line_id, id"`.
- **Verification**:
  - Check `ctkm_task_views.xml` syntax and verify `search_default_group_program_id` is present and `search_default_is_current_stage_task` is removed from default context.

---

### Task 2: Implement Backend Matrix RPC Method `get_user_store_progress_matrix`

- **Files to modify**:
  - `custom_addons/ctkm_core/models/ctkm_task.py`
- **Action**:
  1. Add `@api.model def get_user_store_progress_matrix(self):`
  2. Resolve current user's stores:
     - Check `hr.employee.managed_store_ids` for current user.
     - Check `user.assigned_ma_bo_phan_ids` (LUG Permission).
     - Check `user.employee_ids.ma_bo_phan_id` / `store_id`.
     - If user is manager / admin or has no specific stores assigned, query distinct stores across active programs.
  3. Query active programs where user has tasks:
     - Programs with state not in `['draft', 'cancel']`.
  4. For each (program, store) pair:
     - Evaluate store-level records across stages 9 through 16:
       - Step 9 (In tem): `print_store_ids`
       - Step 10 (Bàn giao/thu tem): `handover_store_ids`, `collect_store_ids`
       - Step 11 & 12 (Nhận tem, Thay tem): `tem_tag_replace_ids`
       - Step 13 & 14 (Chụp ảnh, Kiểm tra): `photo_store_ids` / photo check
       - Step 15 (Áp giá): `price_store_ids`
       - Step 16 (Hậu kiểm): `postcheck_store_ids`
     - Find the earliest active unfinished step (or marked as `Hoàn thành` if all are done).
     - Determine state (`todo`, `progress`, `waiting_confirm`, `done`), state label (`Chưa bắt đầu`, `Đang làm`, `Chờ xác nhận`, `Hoàn thành`), and `badge_class` (`secondary`, `warning`, `info`, `success`), plus `task_id`.
  5. Return formatted dictionary:
     `{'has_data': bool, 'stores': [...], 'programs': [...]}`
- **Verification**:
  - Run python command or scratch script verifying the method executes cleanly and returns the expected dictionary structure without errors.

---

### Task 3: Build Frontend OWL Component & Custom List Controller

- **Files to create**:
  - `custom_addons/ctkm_core/static/src/js/ctkm_task_list_matrix.js`
  - `custom_addons/ctkm_core/static/src/xml/ctkm_task_list_matrix.xml`
  - `custom_addons/ctkm_core/static/src/scss/ctkm_task_list_matrix.scss`
- **Action**:
  1. `ctkm_task_list_matrix.js`:
     - Define `CtkmStoreProgressMatrix` OWL Component:
       - State: `collapsed` (retrieved/persisted in `localStorage.getItem('ctkm_matrix_collapsed')`), `loading`, `matrixData`, `selectedCell`.
       - Methods: `loadMatrix()`, `toggleCollapse()`, `onCellClick(program, cell)`.
       - Cell click behavior: triggers list filter for that program and optionally task, and provides direct `[Mở công việc]` action via `this.actionService.doAction`.
     - Define `CtkmTaskListMatrixController` extending `ListController`:
       - Embeds `<CtkmStoreProgressMatrix>` in its template before the list renderer.
     - Register `ctkm_task_list_with_matrix` in `views` registry.
  2. `ctkm_task_list_matrix.xml`:
     - Render card header with title `Tiến độ theo cửa hàng` (strictly NO icons or emojis).
     - Action buttons: text `[Làm mới]`, `[Thu gọn]` / `[Mở rộng]`.
     - Table container: `table-responsive`, horizontal scroll, sticky CTKM column, sticky header row.
     - Cells: plain text badge with classes (`badge bg-success`, `badge bg-warning`, `badge bg-info`, `badge bg-secondary`).
     - Empty state: clean text `Chưa có dữ liệu cửa hàng cần theo dõi.`
  3. `ctkm_task_list_matrix.scss`:
     - Max height `350px`, overflow-y auto.
     - Sticky first column and sticky header styling.
     - Cursor pointer and hover highlight on clickable cells.
- **Verification**:
  - Verify zero icons or emojis in any JS or XML strings.
  - Verify syntax and exports.

---

### Task 4: Connect View, Assets & Manifest

- **Files to modify**:
  - `custom_addons/ctkm_core/views/ctkm_task_views.xml`:
    - Add `js_class="ctkm_task_list_with_matrix"` to `view_ctkm_task_list`.
  - `custom_addons/ctkm_core/__manifest__.py`:
    - Add `'ctkm_core/static/src/js/ctkm_task_list_matrix.js'`
    - Add `'ctkm_core/static/src/xml/ctkm_task_list_matrix.xml'`
    - Add `'ctkm_core/static/src/scss/ctkm_task_list_matrix.scss'`
    - Bump version to `'4.31'`.
- **Verification**:
  - Verify manifest syntax and file paths exist.

---

### Task 5: End-to-End Testing & Verification

- **Action**:
  1. Run Python verification script to ensure no regressions in `ctkm.task` and test `get_user_store_progress_matrix()`.
  2. Confirm XML files parse without error.
  3. Verify code compliance with no-icon rule.
  4. Git commit all changes.
