import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

import time

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

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    # Show portfolio of stocks

    id = session["user_id"]
    # Query portfolio table to return all of the current user's stocks
    portfolio = db.execute("SELECT * FROM portfolio WHERE userID = :id AND shares <> 0;", id=id)

    # Initialize portfolio total to $0
    portfolio_total = 0

    # For each stock returned in portfolio: call lookup() to find stock price and calculate total value of stock
    for stock in portfolio:
        api_response = lookup(stock["symbol"])
        price = api_response["price"]
        total = float(stock["shares"]) * price
        x = {"price":usd(price), "total":usd(total)}
        stock.update(x)
        portfolio_total += total

    # Get user's current cash
    rows = db.execute("SELECT cash FROM users WHERE id = :id", id=id)
    cash = rows[0]["cash"]

    # Convert cash to USD format
    cash_usd = usd(cash)

    # Calculate portfolio total value by adding cash amount
    portfolio_total += cash

    # Convert portfolio total to USD format
    portfolio_total_usd = usd(portfolio_total)

    # Return index.html with portfolio, cash, and portfolio total variables
    return render_template("index.html", cash=cash_usd, portfolio=portfolio, portfolio_total=portfolio_total_usd)

@app.route("/register", methods=["GET", "POST"])
def register():
    # Register user

    # register() called with "POST" method
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username:
            return apology("Must enter a username", 403)
        elif not password:
            return apology("Must enter a password", 403)
        elif not confirmation:
            return apology("Must confirm password", 403)
        elif password != confirmation:
            return apology("Passwords do not match", 403)
        else:
            count = 0
            numeric = 0
            symbol = 0
            special = "''', '~', '!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '-', '_', '=', '+', '[', '{', '}', ']', '/', '|', '<', ',', '.', '>', '/', '?'"

            for character in password:
                if character.isalpha() == True or character.isspace() == True:
                    count += 1
                elif character.isnumeric() == True:
                    count += 1
                    numeric += 1
                elif character in special:
                    count += 1
                    symbol += 1
                else:
                    return apology("Invalid character in password.")

            if count < 8 or numeric < 1 or symbol < 1:
                return apology("Password requires at least 8 characters, including at least 1 number and 1 symbol")


        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
        if len(rows) > 0:
            return apology("User already exists", 403)

        # Hash password
        hash = generate_password_hash(password)

        # Update db with user and password hash
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)

        # Query db to find new user
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)

        # Set user_id for this session equal to the id value of the query result
        session["user_id"] = rows[0]["id"]

        # Direct user to home page
        flash("You have successfully registered! Welcome " + username +"!")
        return redirect("/")


    # register() called with "GET" method
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Log user in

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
        flash("Welcome back " + request.form.get("username") + "!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    # Log user out

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        response = lookup(symbol)
        if not response:
            return apology("Invalid Stock Symbol")
        else:
            name = response["name"]
            price = usd(response["price"])
            symbol = response["symbol"]
            return render_template("quote.html", name=name, price=price, symbol=symbol)
    else:
        return render_template("quote.html")



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # /buy called with POST method
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("You Must Input a Stock Symbol")
        elif not request.form.get("shares"):
            return apology("You Must Input the Number of Shares You Wish to Purchase")
        else:
            symbol = request.form.get("symbol")
            try:
                shares = int(request.form.get("shares"))
            except ValueError:
                return apology("The Number of Shares Must be a Whole Number Greater than 0")
            if shares < 1:
                return apology("The Number of Shares Must be a Whole Number Greater than 0")


        response = lookup(symbol)

        if not response:
            return apology("Invalid Stock Symbol")
        else:
            company = response["name"]
            price = response["price"]
            price_usd = usd(price)
            symbol = response["symbol"]
            id = session["user_id"]
            # Query database to get user's current cash
            rows = db.execute("SELECT cash FROM users where id = :id", id=id)
            cash = rows[0]["cash"]
            # Compare cash to total cost of stock (Price * Number of Shares)
            cost = price * float(shares)
            if cost > cash:
                return apology("You do not have enough cash for this purchase")

            # If user can buy, update buy table with user, stock, shares, and time
            else:
                ts = time.time()
                ts = time.ctime(ts)
                db.execute("INSERT INTO transactions (userID, symbol, company, shares, price, transactiontype, transactiontime) VALUES (:userID, :symbol, :company, :shares, :price, :transactiontype, :transactiontime);", userID=id, symbol=symbol, company=company, shares=shares, price=price, transactiontype="BUY", transactiontime=ts)

                # Update user table for new cash amount
                remaining = cash - cost
                db.execute("UPDATE users SET cash = :remaining WHERE id = :id;", remaining=remaining, id=id)

                # Update number of shares owned in portfolio table for user and stock symbol
                portfolio = db.execute("SELECT * FROM portfolio WHERE userID = :id AND symbol = :symbol;", id=id, symbol=symbol)
                if (len(portfolio)) == 1:
                    # Update existing row in portfolio for user and symbol
                    updated_shares = portfolio[0]["shares"] + shares
                    db.execute("UPDATE portfolio SET shares = :updated_shares WHERE userID = :userID AND symbol = :symbol;", updated_shares=updated_shares, userID=id, symbol=symbol)
                else:
                    # Create row in portfolio for user and symbol
                    db.execute("INSERT INTO portfolio (userID, symbol, company, shares) VALUES (:id, :symbol, :company, :shares);", id=id, symbol=symbol, company=company, shares=shares)

                cost_usd = usd(cost)
                remaining_usd = usd(remaining)
                flash("Success! You purchased " + str(shares) + " share(s) of " + company + " (" + symbol + ") at " + price_usd + " per share for a total of " + cost_usd + ".")
                flash("You have " + remaining_usd + " remaining.")
                return redirect("/")

    # /buy called with GET method
    else:
        return render_template("buy.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    # Sell shares of stock
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("You Must Input a Stock Symbol")
        elif not request.form.get("shares"):
            return apology("You Must Input the Number of Shares You Wish to Sell")
        else:
            symbol = request.form.get("symbol")
            try:
                shares = int(request.form.get("shares"))
            except ValueError:
                return apology("The Number of Shares Must be a Whole Number Greater than 0")
            if shares < 1:
                return apology("The Number of Shares Must be a Whole Number Greater than 0")

        id = session["user_id"]

        portfolio = db.execute("SELECT * FROM portfolio WHERE userID = :id AND symbol = :symbol", id=id, symbol=symbol)

        if portfolio[0]["shares"] < shares:
            return apology("You do not have enough shares")

        api_response = lookup(symbol)
        price = api_response["price"]
        company = api_response["name"]

        ts = time.time()
        ts = time.ctime(ts)
        db.execute("INSERT INTO transactions (userID, symbol, company, shares, price, transactiontype, transactiontime) VALUES (:userID, :symbol, :company, :shares, :price, :transactiontype, :transactiontime);", userID=id, symbol=symbol, company=company, shares=shares * -1, price=price, transactiontype="SELL", transactiontime=ts)


        updated_shares = portfolio[0]["shares"] - shares
        db.execute("UPDATE portfolio SET shares = :updated_shares WHERE userID = :userID AND symbol = :symbol;", updated_shares=updated_shares, userID=id, symbol=symbol)

        rows = db.execute("SELECT * FROM users WHERE id = :userID;", userID=id)
        gain = float(shares) * price
        updated_cash = rows[0]["cash"] + gain

        price_usd = usd(price)
        gain_usd = usd(gain)
        db.execute("UPDATE users SET cash = :updated_cash WHERE id = :userID;", updated_cash=updated_cash, userID=id)

        flash("Success! You sold " + str(shares) + " share(s) of " + company + " (" + symbol + ") at " + price_usd + " per share for a total of " + gain_usd +".")
        return redirect("/")

    else:
        portfolio = db.execute("SELECT * FROM portfolio WHERE userID = :id AND shares <> 0",id=session["user_id"])
        return render_template("sell.html", portfolio=portfolio)



@app.route("/history")
@login_required
def history():
    # Show history of transactions

    id = session["user_id"]

    # Query transactions table for all current user's transactions
    transactions = db.execute("SELECT * FROM transactions WHERE userID = :userID", userID=id)

    # Convert price into USD format for each transaction
    for stock in transactions:
        stock["price"] = usd(stock["price"])

    # Render history.html and pass transactions list as input
    return render_template("history.html", transactions=transactions)



def errorhandler(e):
    # Handle error
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
