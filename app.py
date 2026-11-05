from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import date
from mysql.connector import IntegrityError
from db import get_connection

app = Flask(__name__)
app.secret_key = "library-book-project-secret-key"


# HOME PAGE
@app.route("/")
def home():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) AS total FROM books")
        total_books = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM borrowers")
        total_borrowers = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loans
            WHERE return_date IS NULL
        """)
        currently_issued = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loans
            WHERE return_date IS NULL
              AND due_date < CURDATE()
        """)
        overdue_books = cursor.fetchone()["total"]

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "index.html",
        total_books=total_books,
        total_borrowers=total_borrowers,
        currently_issued=currently_issued,
        overdue_books=overdue_books
    )


# BOOKS PAGE WITH SEARCH
@app.route("/books", methods=["GET", "POST"])
def books():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # ADD A BOOK
        if request.method == "POST":
            isbn = request.form.get("isbn", "").strip() or None
            title = request.form.get("title", "").strip()
            author = request.form.get("author", "").strip()
            category = request.form.get("category", "").strip() or None

            try:
                copies = int(request.form.get("copies", "1"))
            except ValueError:
                flash(
                    "Number of copies must be a valid whole number.",
                    "error"
                )
                return redirect(url_for("books"))

            if not title or not author or copies < 0:
                flash(
                    "Enter a valid title, author, and number of copies.",
                    "error"
                )
                return redirect(url_for("books"))

            try:
                cursor.execute("""
                    INSERT INTO books
                    (isbn, title, author, category, copies_available)
                    VALUES (%s, %s, %s, %s, %s)
                """, (isbn, title, author, category, copies))

                connection.commit()
                flash("Book added successfully!", "success")

            except IntegrityError as error:
                connection.rollback()

                if error.errno == 1062:
                    flash(
                        "This ISBN already exists. Please use a different ISBN.",
                        "error"
                    )
                else:
                    raise

            return redirect(url_for("books"))

        # SEARCH BOOKS
        search = request.args.get("search", "").strip()

        if search:
            keyword = f"%{search}%"

            cursor.execute("""
                SELECT *
                FROM books
                WHERE title LIKE %s
                   OR author LIKE %s
                   OR isbn LIKE %s
                ORDER BY book_id DESC
            """, (keyword, keyword, keyword))

        else:
            cursor.execute("""
                SELECT *
                FROM books
                ORDER BY book_id DESC
            """)

        all_books = cursor.fetchall()

        return render_template(
            "books.html",
            books=all_books
        )

    finally:
        cursor.close()
        connection.close()


# BORROWERS PAGE WITH SEARCH
@app.route("/borrowers", methods=["GET", "POST"])
def borrowers():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # REGISTER A BORROWER
        if request.method == "POST":
            name = request.form.get("borrower_name", "").strip()
            roll_no = request.form.get("roll_no", "").strip()

            if not name or not roll_no:
                return "Enter both student name and roll number.", 400

            cursor.execute("""
                INSERT INTO borrowers (borrower_name, roll_no)
                VALUES (%s, %s)
            """, (name, roll_no))

            connection.commit()

            return redirect(url_for("borrowers"))

        # GET SEARCH INPUT
        search = request.args.get("search", "").strip()

        # SEARCH BY NAME OR ROLL NUMBER
        if search:
            keyword = f"%{search}%"

            cursor.execute("""
                SELECT *
                FROM borrowers
                WHERE borrower_name LIKE %s
                   OR roll_no LIKE %s
                ORDER BY borrower_id DESC
            """, (keyword, keyword))

        else:
            cursor.execute("""
                SELECT *
                FROM borrowers
                ORDER BY borrower_id DESC
            """)

        all_borrowers = cursor.fetchall()

        return render_template(
            "borrowers.html",
            borrowers=all_borrowers
        )

    finally:
        cursor.close()
        connection.close()


# ISSUE BOOKS
@app.route("/loans", methods=["GET", "POST"])
def loans():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if request.method == "POST":
            borrower_id = request.form.get("borrower_id", "").strip()
            book_id = request.form.get("book_id", "").strip()
            issue_date = request.form.get("issue_date", "").strip()
            due_date = request.form.get("due_date", "").strip()

            # VALIDATE IDS
            try:
                borrower_id = int(borrower_id)
                book_id = int(book_id)
            except ValueError:
                return "Select a valid book and borrower.", 400

            # VALIDATE DATES
            try:
                parsed_issue_date = date.fromisoformat(issue_date)
                parsed_due_date = date.fromisoformat(due_date)
            except ValueError:
                return "Enter valid issue and due dates.", 400

            if parsed_due_date < parsed_issue_date:
                return "Due date cannot be before issue date.", 400

            try:
                connection.start_transaction()

                # CHECK BOOK AVAILABILITY
                cursor.execute("""
                    SELECT copies_available
                    FROM books
                    WHERE book_id = %s
                    FOR UPDATE
                """, (book_id,))

                book = cursor.fetchone()

                if not book or book["copies_available"] <= 0:
                    connection.rollback()
                    return "This book is not available.", 400

                # CHECK BORROWER EXISTS
                cursor.execute("""
                    SELECT borrower_id
                    FROM borrowers
                    WHERE borrower_id = %s
                """, (borrower_id,))

                borrower = cursor.fetchone()

                if not borrower:
                    connection.rollback()
                    return "Student not found.", 400

                # SAVE LOAN
                cursor.execute("""
                    INSERT INTO loans
                    (book_id, borrower_id, issue_date, due_date)
                    VALUES (%s, %s, %s, %s)
                """, (
                    book_id,
                    borrower_id,
                    parsed_issue_date,
                    parsed_due_date
                ))

                # DECREASE AVAILABLE COPIES
                cursor.execute("""
                    UPDATE books
                    SET copies_available = copies_available - 1
                    WHERE book_id = %s
                """, (book_id,))

                connection.commit()

            except Exception:
                connection.rollback()
                raise

            return redirect(url_for("loans"))

        # GET BOOKS FOR THE ISSUE FORM
        cursor.execute("""
            SELECT *
            FROM books
            ORDER BY title
        """)
        all_books = cursor.fetchall()

        # GET BORROWERS FOR THE ISSUE FORM
        cursor.execute("""
            SELECT *
            FROM borrowers
            ORDER BY borrower_name
        """)
        all_borrowers = cursor.fetchall()

        # GET LOAN RECORDS
        cursor.execute("""
            SELECT
                loans.*,
                books.title,
                borrowers.borrower_name
            FROM loans
            JOIN books ON loans.book_id = books.book_id
            JOIN borrowers ON loans.borrower_id = borrowers.borrower_id
            ORDER BY loans.loan_id DESC
        """)

        all_loans = cursor.fetchall()

        return render_template(
            "loans.html",
            books=all_books,
            borrowers=all_borrowers,
            loans=all_loans
        )

    finally:
        cursor.close()
        connection.close()


# RETURN BOOK
@app.route("/return_book/<int:loan_id>", methods=["POST"])
def return_book(loan_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        # FIND THE LOAN
        cursor.execute("""
            SELECT *
            FROM loans
            WHERE loan_id = %s
            FOR UPDATE
        """, (loan_id,))

        loan = cursor.fetchone()

        if not loan:
            connection.rollback()
            return "Borrowing record not found.", 404

        # PREVENT RETURNING TWICE
        if loan["return_date"] is not None:
            connection.rollback()
            return "This book has already been returned.", 400

        # UPDATE RETURN DATE
        cursor.execute("""
            UPDATE loans
            SET return_date = %s
            WHERE loan_id = %s
        """, (date.today(), loan_id))

        # RESTORE AVAILABLE COPIES
        cursor.execute("""
            UPDATE books
            SET copies_available = copies_available + 1
            WHERE book_id = %s
        """, (loan["book_id"],))

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("loans"))


# LOAN MANAGEMENT WITH SEARCH AND STATUS FILTER
@app.route("/loan-management")
def loan_management():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        search = request.args.get("search", "").strip()
        status = request.args.get("status", "all").strip().lower()

        # BUILD THE QUERY
        query = """
            SELECT
                loans.loan_id,
                loans.issue_date,
                loans.due_date,
                loans.return_date,
                books.title,
                borrowers.borrower_name,
                borrowers.roll_no,
                CASE
                    WHEN loans.return_date IS NOT NULL THEN 'Returned'
                    WHEN loans.due_date < CURDATE() THEN 'Overdue'
                    ELSE 'Issued'
                END AS loan_status
            FROM loans
            JOIN books ON loans.book_id = books.book_id
            JOIN borrowers ON loans.borrower_id = borrowers.borrower_id
            WHERE 1 = 1
        """

        params = []

        # SEARCH BY BOOK, STUDENT NAME, OR ROLL NUMBER
        if search:
            keyword = f"%{search}%"

            query += """
                AND (
                    books.title LIKE %s
                    OR borrowers.borrower_name LIKE %s
                    OR borrowers.roll_no LIKE %s
                )
            """

            params.extend([keyword, keyword, keyword])

        # FILTER BY STATUS
        if status == "issued":
            query += """
                AND loans.return_date IS NULL
                AND loans.due_date >= CURDATE()
            """

        elif status == "overdue":
            query += """
                AND loans.return_date IS NULL
                AND loans.due_date < CURDATE()
            """

        elif status == "returned":
            query += " AND loans.return_date IS NOT NULL"

        query += " ORDER BY loans.loan_id DESC"

        cursor.execute(query, tuple(params))
        all_loans = cursor.fetchall()

        return render_template(
            "loan_management.html",
            loans=all_loans,
            today=date.today().isoformat(),
            search=search,
            status=status
        )

    finally:
        cursor.close()
        connection.close()


# ANALYTICS DASHBOARD
@app.route("/analytics")
def analytics():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # TOTAL BOOKS
        cursor.execute("SELECT COUNT(*) AS total FROM books")
        total_books = cursor.fetchone()["total"]

        # TOTAL BORROWERS
        cursor.execute("SELECT COUNT(*) AS total FROM borrowers")
        total_borrowers = cursor.fetchone()["total"]

        # CURRENTLY ISSUED BOOKS
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loans
            WHERE return_date IS NULL
        """)
        currently_issued = cursor.fetchone()["total"]

        # OVERDUE BOOKS
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM loans
            WHERE return_date IS NULL
              AND due_date < CURDATE()
        """)
        overdue_books = cursor.fetchone()["total"]

        # MOST POPULAR BOOKS
        cursor.execute("""
            SELECT
                books.title,
                COUNT(loans.loan_id) AS borrow_count
            FROM loans
            JOIN books ON loans.book_id = books.book_id
            GROUP BY books.book_id, books.title
            ORDER BY borrow_count DESC, books.title
            LIMIT 10
        """)
        popular_books = cursor.fetchall()

        # MONTHLY BORROWING TRENDS
        cursor.execute("""
            SELECT
                DATE_FORMAT(issue_date, '%Y-%m') AS month,
                COUNT(*) AS borrow_count
            FROM loans
            GROUP BY DATE_FORMAT(issue_date, '%Y-%m')
            ORDER BY month
        """)
        monthly_trends = cursor.fetchall()

        # CATEGORY STATISTICS
        cursor.execute("""
            SELECT
                COALESCE(books.category, 'Uncategorized') AS category,
                COUNT(loans.loan_id) AS borrow_count
            FROM loans
            JOIN books ON loans.book_id = books.book_id
            GROUP BY COALESCE(books.category, 'Uncategorized')
            ORDER BY borrow_count DESC, category
        """)
        category_stats = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "analytics.html",
        total_books=total_books,
        total_borrowers=total_borrowers,
        currently_issued=currently_issued,
        overdue_books=overdue_books,
        popular_books=popular_books,
        monthly_trends=monthly_trends,
        category_stats=category_stats
    )


# RUN THE APPLICATION
if __name__ == "__main__":
    app.run(debug=True)
