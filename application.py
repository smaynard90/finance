import os
import sqlalchemy
import urllib.parse
import psycopg2

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQL database
db = SQL(os.getenv("DATABASE_URL"))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query user's cash balance and convert to USD
    cash_sql = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    cash = usd(cash_sql[0]['cash'])

    # Query user's stock information
    stocks = db.execute("SELECT symbol, name, SUM(shares) FROM portfolio WHERE user_id = ? GROUP BY symbol, name", session["user_id"])

    # Set stock subtotal to $0
    subtotal = 0.0

    # Adds stocks' market prices to user's stock array
    for stock in stocks:

        # Collects data for each stock in the array
        quote = lookup(stock["symbol"])

        # Converts each stock's market price to USD and adds to the array
        stock["price"] = (usd(quote["price"]))

        # Calculates total value of shares, formatted as USD
        stock["total"] = usd(((float(stock["SUM(shares)"])) * quote["price"]))

        # Calculates total value of stocks
        subtotal += ((float(stock["SUM(shares)"])) * quote["price"])

    # Calculates grand total, formatted as USD
    grand_total = usd(cash_sql[0]['cash'] + subtotal)

    # Displays user's stock portfolio
    return render_template("portfolio.html", cash=cash, stocks=stocks, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # Sends user to buy.html if they click "Buy" in the header
    if request.method == "GET":
        return render_template("buy.html")

    # Buys stock(s)
    else:

        # Looks up user's symbol and stores buying information in Python variables
        symbol = request.form.get("symbol")
        shares_str = request.form.get("shares")
        shares = 0
        quote = None

        # Converts shares from string to integer if possble
        if shares_str.isnumeric():
            shares = int(shares_str)

        # Looks up symbol's stock information if symbol is valid
        if symbol:
            quote = lookup(symbol)
            if quote:
                price = float(quote['price'])
                cost = price * float(shares)

        # Returns an apology if user's symbol is invalid
        if not quote or not symbol:
            return apology("Invalid symbol")

        # Returns an apology if user's shares are invalid
        elif not shares:
            return apology("Missing shares")

        # Checks user's cash balance
        else:
            balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
            float_balance = float(balance[0]['cash'])

            # Ensures user's cash balance exceeds cost of stock(s)
            if float_balance < cost:
                return apology("Not enough funds!")

            # Adds stock(s) to user's portfolio in a new table (if table doesn't already exist)
            else:
                total = float_balance - cost
                now = datetime.datetime.now()
                transacted = now.replace(microsecond = 0)
                db.execute("CREATE TABLE IF NOT EXISTS portfolio (id INTEGER PRIMARY KEY, user_id INTEGER, symbol TEXT, name TEXT, shares INTEGER, price REAL, transacted NUMERIC, total REAL)")
                db.execute("INSERT INTO portfolio (user_id, symbol, name, shares, price, transacted, total) VALUES(?, ?, ?, ?, ?, ?, ?)",
                           session['user_id'], quote['symbol'], quote['name'], shares, price, transacted, total)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", total, session["user_id"])
                return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Sends user to sell.html if they click "Sell" in the header
    if request.method == "GET":

        # Queries and displays user's transaction history
        history = db.execute("SELECT symbol, shares, price, transacted FROM portfolio WHERE user_id = ? ORDER BY transacted ASC", session["user_id"])

        # Converts each stock's market price to USD and adds to the array
        for row in history:
            row["price"] = (usd(row["price"]))

        return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # Sends user to quote.html if they click "Register" in the header
    if request.method == "GET":
        return render_template("quote.html")

    # Submits user's symbol from quote.html
    else:

        # Looks up user's symbol and stores information in Python variables
        symbol = request.form.get("symbol")
        quote = lookup(symbol)

        # Ensures user's symbol is valid
        if not quote:
            return apology("Invalid Symbol")

        # Quotes user's symbol
        else:
            return render_template("quoted.html", name=quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Sends user to register.html if they click "Register" in the header
    if request.method == "GET":
        return render_template("register.html")

    # Submits user's username and password from register.html
    else:

        # Stores user's username, password, and confirmation into Python variables
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensures fields aren't left blank
        if not username:
            return apology("Missing username!")
        if not password:
            return apology("Missing password!")
        if not confirmation:
            return apology("Missing password confirmation!")

        # Ensures password matches confirmation
        else:
            if password != confirmation:
                return apology("Passwords don't match")

            else:
                # Hashes password
                hash = generate_password_hash(password)

                # Inserts username and hashed password into database
                result = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=hash)

                # Ensures username is available
                if not result:
                    return apology("Username is not available")

                # Query database for username
                rows = db.execute("SELECT * FROM users WHERE username = :username",
                                  username = request.form.get("username"))

                # Logs user in
                session["user_id"] = rows[0]["id"]
                return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Checks user's cash balance
    balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    float_balance = float(balance[0]['cash'])

    # Query user's stock information
    stocks = db.execute("SELECT symbol, name, SUM(shares) FROM portfolio WHERE user_id = ? GROUP BY symbol", session["user_id"])

    # Adds stocks' market prices to user's stock array
    for stock in stocks:

        # Collects data for each stock in the array
        quote = lookup(stock["symbol"])

        # Converts each stock's market price to USD and adds to the array
        stock["price"] = (usd(quote["price"]))

        # Calculates total value of shares, formatted as USD
        stock["total"] = usd((float(stock["SUM(shares)"])) * quote["price"])

    # Sends user to sell.html if they click "Sell" in the header
    if request.method == "GET":
        return render_template("sell.html", stocks=stocks)

    # Sells stock(s)
    else:

        # Stores user's stock information into Python variables
        symbol = request.form.get("symbol")
        shares_str = request.form.get("shares")
        shares = 0

        if shares_str.isnumeric():
            shares = int(shares_str)

        if symbol:
            quote = lookup(symbol)
            price = float(quote['price'])
            cost = price * float(shares)
            total = float_balance + cost
            now = datetime.datetime.now()
            transacted = now.replace(microsecond = 0)

        # Returns an apology if user fails to select a stock
        if not symbol:
            return apology("Missing symbol")

        # Returns an apology if user fails to input shares
        elif not shares:
            return apology("Missing shares")

        # Returns an apology if the user does not own enough shares of selected stock
        elif symbol:
            contains = False
            sum_shares = 0
            for stock in stocks:
                if symbol == stock['symbol']:
                    contains = True
                    sum_shares = stock['SUM(shares)']
            if not contains:
                return apology("Symbol doesn't exist")
            elif contains:
                if sum_shares == 0 or sum_shares < shares:
                    return apology("Too many shares")

        # Returns an apology if inputted shares is not a positive integer
        elif shares < 1 or not isinstance(shares, int):
            return apology("Shares must be a positive integer")

        # Converts shares to a negative number to insert in database
        shares *= -1

        db.execute("INSERT INTO portfolio (user_id, symbol, name, shares, price, transacted, total) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   session['user_id'], quote['symbol'], quote['name'], shares, price, transacted, total)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", total, session["user_id"])

        return redirect("/")

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Deposit funds"""

    # Sends user to deposit.html if they click "Deposit" in the header
    if request.method == "GET":
        return render_template("deposit.html")

    # Deposits funds into user's account
    else:

        # Stores user's stock information into Python variables
        deposit = float(request.form.get("deposit"))

        if deposit > 10000:
            return apology("Must deposit $10,000 or less")

        elif deposit < 0.01:
            return apology("Must deposit at least $0.01")

        else:
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", deposit, session["user_id"])
            return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

if __name__ == '__main__':
    app.debug = True
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
