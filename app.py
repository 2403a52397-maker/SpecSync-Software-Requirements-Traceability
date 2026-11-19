from flask import Flask, render_template, request, redirect, url_for
from database import initialize_database, get_db_connection

app = Flask(__name__)
initialize_database()


def redirect_to(endpoint):
    return redirect(url_for(endpoint))


@app.route("/")
def home():
    conn = get_db_connection()
    stats = {
        "total_projects": conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "total_requirements": conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0],
        "total_versions": conn.execute("SELECT COUNT(*) FROM requirement_versions").fetchone()[0],
        "total_test_cases": conn.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0],
    }
    projects = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("dashboard.html", projects=projects, **stats)


@app.route("/projects")
def projects():
    return redirect(url_for("home", _anchor="projects"))


@app.route("/add_project", methods=["POST"])
def add_project():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    if not name:
        return redirect(url_for("home"))
    # Normalize known typo and prevent duplicate project names (case-insensitive).
    if name.lower() in {"student mangement", "student managment"}:
        name = "student management"
    conn = get_db_connection()
    exists = conn.execute("SELECT 1 FROM projects WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
    if not exists:
        conn.execute("INSERT INTO projects (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/delete_project/<int:project_id>", methods=["POST"])
def delete_project(project_id):
    conn = get_db_connection()
    # Explicit deletes also work with older databases that lack cascading FK enforcement.
    conn.execute("""DELETE FROM traceability_links
        WHERE requirement_id IN (SELECT id FROM requirements WHERE project_id=?)
        OR test_case_id IN (SELECT id FROM test_cases WHERE project_id=?)""",
        (project_id, project_id))
    conn.execute("DELETE FROM requirement_versions WHERE requirement_id IN (SELECT id FROM requirements WHERE project_id=?)", (project_id,))
    conn.execute("DELETE FROM requirements WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM test_cases WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/requirements")
def requirements():
    conn = get_db_connection()
    projects = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    all_requirements = conn.execute("""
        SELECT r.*, p.name AS project_name
        FROM requirements r JOIN projects p ON p.id=r.project_id
        ORDER BY r.id DESC
    """).fetchall()
    conn.close()
    return render_template("requirements.html", projects=projects, requirements=all_requirements)


@app.route("/add_requirement", methods=["POST"])
def add_requirement():
    project_id = request.form.get("project_id", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    req_type = request.form.get("requirement_type", "").strip()
    priority = request.form.get("priority", "Medium").strip() or "Medium"
    if not project_id or not title or req_type not in {"Functional", "Non-Functional"}:
        return redirect(url_for("requirements"))
    try:
        project_id = int(project_id)
    except ValueError:
        return redirect(url_for("requirements"))

    conn = get_db_connection()
    if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        return redirect(url_for("requirements"))
    cur = conn.execute("""
        INSERT INTO requirements (project_id,title,description,requirement_type,priority,version)
        VALUES (?,?,?,?,?,1)
    """, (project_id, title, description, req_type, priority))
    req_id = cur.lastrowid
    conn.execute("""
        INSERT INTO requirement_versions (requirement_id,version_number,title,description)
        VALUES (?,1,?,?)
    """, (req_id, title, description))
    conn.commit()
    conn.close()
    return redirect(url_for("requirements"))


@app.route("/update_requirement/<int:requirement_id>", methods=["POST"])
def update_requirement(requirement_id):
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    req_type = request.form.get("requirement_type", "").strip()
    priority = request.form.get("priority", "Medium").strip() or "Medium"
    if not title or req_type not in {"Functional", "Non-Functional"}:
        return redirect(url_for("requirements"))

    conn = get_db_connection()
    current = conn.execute("SELECT * FROM requirements WHERE id=?", (requirement_id,)).fetchone()
    if current is None:
        conn.close()
        return redirect(url_for("requirements"))

    changed = (current["title"] != title or current["description"] != description
               or current["requirement_type"] != req_type or current["priority"] != priority)
    if changed:
        # Store the NEW state as the next version, keeping earlier snapshots unchanged.
        next_version = max(
            current["version"] or 1,
            conn.execute("SELECT COALESCE(MAX(version_number),0) FROM requirement_versions WHERE requirement_id=?",
                         (requirement_id,)).fetchone()[0]
        ) + 1
        conn.execute("""
            INSERT INTO requirement_versions (requirement_id,version_number,title,description)
            VALUES (?,?,?,?)
        """, (requirement_id, next_version, title, description))
        conn.execute("""
            UPDATE requirements
            SET title=?, description=?, requirement_type=?, priority=?, version=?
            WHERE id=?
        """, (title, description, req_type, priority, next_version, requirement_id))
    conn.commit()
    conn.close()
    return redirect(url_for("requirements"))


@app.route("/delete_requirement/<int:requirement_id>", methods=["POST"])
def delete_requirement(requirement_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM traceability_links WHERE requirement_id=?", (requirement_id,))
    conn.execute("DELETE FROM requirement_versions WHERE requirement_id=?", (requirement_id,))
    conn.execute("DELETE FROM requirements WHERE id=?", (requirement_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("requirements"))


@app.route("/versions")
def versions():
    conn = get_db_connection()
    all_versions = conn.execute("""
        SELECT rv.*, r.title AS requirement_title, p.name AS project_name
        FROM requirement_versions rv
        JOIN requirements r ON rv.requirement_id=r.id
        JOIN projects p ON r.project_id=p.id
        ORDER BY rv.requirement_id DESC, rv.version_number DESC
    """).fetchall()
    conn.close()
    return render_template("versions.html", versions=all_versions)


@app.route("/test_cases")
def test_cases():
    conn = get_db_connection()
    projects = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    all_test_cases = conn.execute("""
        SELECT t.*, p.name AS project_name
        FROM test_cases t JOIN projects p ON p.id=t.project_id
        ORDER BY t.id DESC
    """).fetchall()
    conn.close()
    return render_template("test_cases.html", projects=projects, test_cases=all_test_cases)


@app.route("/add_test_case", methods=["POST"])
def add_test_case():
    project_id = request.form.get("project_id", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    expected_result = request.form.get("expected_result", "").strip()
    if not project_id or not title:
        return redirect(url_for("test_cases"))
    try:
        project_id = int(project_id)
    except ValueError:
        return redirect(url_for("test_cases"))
    conn = get_db_connection()
    if not conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        conn.close()
        return redirect(url_for("test_cases"))
    conn.execute("""
        INSERT INTO test_cases (project_id,title,description,expected_result,status)
        VALUES (?,?,?,?, 'Not Executed')
    """, (project_id, title, description, expected_result))
    conn.commit()
    conn.close()
    return redirect(url_for("test_cases"))


@app.route("/update_test_case_status/<int:test_case_id>", methods=["POST"])
def update_test_case_status(test_case_id):
    status = request.form.get("status", "").strip()
    if status not in {"Pass", "Fail", "Not Executed"}:
        return redirect(url_for("test_cases"))
    conn = get_db_connection()
    conn.execute("UPDATE test_cases SET status=? WHERE id=?", (status, test_case_id))
    conn.commit()
    conn.close()
    return redirect(url_for("test_cases"))


@app.route("/delete_test_case/<int:test_case_id>", methods=["POST"])
def delete_test_case(test_case_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM traceability_links WHERE test_case_id=?", (test_case_id,))
    conn.execute("DELETE FROM test_cases WHERE id=?", (test_case_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("test_cases"))


@app.route("/traceability")
def traceability():
    conn = get_db_connection()
    requirements = conn.execute("""
        SELECT r.id,r.title,r.project_id,p.name AS project_name
        FROM requirements r JOIN projects p ON p.id=r.project_id ORDER BY r.id DESC
    """).fetchall()
    test_cases = conn.execute("""
        SELECT t.id,t.title,t.project_id,p.name AS project_name
        FROM test_cases t JOIN projects p ON p.id=t.project_id ORDER BY t.id DESC
    """).fetchall()
    links = conn.execute("""
        SELECT tl.id,r.title AS requirement_title,p.name AS project_name,t.title AS test_case_title
        FROM traceability_links tl
        JOIN requirements r ON r.id=tl.requirement_id
        JOIN projects p ON p.id=r.project_id
        JOIN test_cases t ON t.id=tl.test_case_id
        ORDER BY tl.id DESC
    """).fetchall()
    conn.close()
    return render_template("traceability.html", requirements=requirements, test_cases=test_cases, links=links)


@app.route("/add_traceability_link", methods=["POST"])
def add_traceability_link():
    req_id = request.form.get("requirement_id", "").strip()
    test_id = request.form.get("test_case_id", "").strip()
    if not req_id or not test_id:
        return redirect(url_for("traceability"))
    conn = get_db_connection()
    # IDs must exist and both items must belong to the same project.
    same_project = conn.execute("""
        SELECT 1 FROM requirements r JOIN test_cases t ON r.project_id=t.project_id
        WHERE r.id=? AND t.id=?
    """, (req_id, test_id)).fetchone()
    if same_project:
        conn.execute("INSERT OR IGNORE INTO traceability_links (requirement_id,test_case_id) VALUES (?,?)",
                     (req_id, test_id))
        conn.commit()
    conn.close()
    return redirect(url_for("traceability"))


@app.route("/delete_traceability_link/<int:link_id>", methods=["POST"])
def delete_traceability_link(link_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM traceability_links WHERE id=?", (link_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("traceability"))


@app.route("/reports")
def reports():
    conn = get_db_connection()
    total_projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    total_requirements = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    total_test_cases = conn.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0]
    total_versions = conn.execute("SELECT COUNT(*) FROM requirement_versions").fetchone()[0]
    total_links = conn.execute("SELECT COUNT(*) FROM traceability_links").fetchone()[0]
    linked_requirements = conn.execute("SELECT COUNT(DISTINCT requirement_id) FROM traceability_links").fetchone()[0]
    coverage = round(linked_requirements * 100.0 / total_requirements, 2) if total_requirements else 0.0

    passed = conn.execute("SELECT COUNT(*) FROM test_cases WHERE status='Pass'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM test_cases WHERE status='Fail'").fetchone()[0]
    not_executed = conn.execute("SELECT COUNT(*) FROM test_cases WHERE status='Not Executed'").fetchone()[0]

    rows = conn.execute("""
        SELECT p.id,p.name,
          (SELECT COUNT(*) FROM requirements r WHERE r.project_id=p.id) AS requirements_count,
          (SELECT COUNT(*) FROM test_cases t WHERE t.project_id=p.id) AS test_cases_count,
          (SELECT COUNT(DISTINCT tl.requirement_id)
             FROM traceability_links tl JOIN requirements r ON r.id=tl.requirement_id
             WHERE r.project_id=p.id) AS linked_count
        FROM projects p ORDER BY p.id DESC
    """).fetchall()
    conn.close()

    project_reports = []
    for row in rows:
        req_count = row["requirements_count"]
        linked_count = row["linked_count"]
        project_reports.append({
            "name": row["name"],
            "requirements_count": req_count,
            "test_cases_count": row["test_cases_count"],
            "linked_count": linked_count,
            "coverage": round(linked_count * 100.0 / req_count, 2) if req_count else 0.0
        })

    return render_template("reports.html", total_projects=total_projects,
        total_requirements=total_requirements, total_test_cases=total_test_cases,
        total_versions=total_versions, total_links=total_links, coverage=coverage,
        passed_test_cases=passed, failed_test_cases=failed,
        not_executed_test_cases=not_executed, project_reports=project_reports)


if __name__ == "__main__":
    app.run(debug=True)
