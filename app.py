import os
import sys
import time
import json
import io
import base64
from jugaad_data.nse import stock_df
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from nsetools import Nse
# from bokeh.plotting import figure, output_file, show
# from bokeh.embed import components
# from bokeh.resources import INLINE

# Create an instance of NSE
nse = Nse()

app = Flask(__name__)
app.secret_key = '2022CS11631'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('stock_analysis'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        session['username'] = user.username
        return redirect(url_for('welcome'))
    else:
        flash('Invalid username or password')
        return redirect(url_for('index'))


@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/process_choice', methods=['POST'])
def process_choice():
    choice = request.form['choice']
    if choice == 'new':
        return redirect(url_for('stock_analysis'))
    elif choice == 'previous':
        return redirect(url_for('display_previous_inputs'))

from flask import render_template

@app.route('/display_previous_inputs')
def display_previous_inputs():
    previous_inputs = session.get('previous_inputs', [])
    return render_template('previous_inputs.html', previous_inputs=previous_inputs)


@app.route('/clear_previous_inputs', methods=['POST'])
def clear_previous_inputs():
    try:
        # Open the file in 'w' mode to clear its contents
        with open('previous_inputs.json', 'w') as file:
            pass  # Do nothing, just clear the file

        # Update the session variable with an empty list
        session['previous_inputs'] = []

        # Return a success message or redirect to the display_previous_inputs page
        return jsonify({'message': 'Previous inputs cleared successfully'})

    except Exception as e:
        # Handle any exceptions that may occur during the process
        return jsonify({'error': str(e)})



@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        return render_template('welcome.html', username=session['username'])
    else:
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('index'))

def plot_data(stock_symbols, time_scale, all_stock_data):
    plt.figure(figsize=(12, 6))

    for stock_symbol in stock_symbols:
        stock_symbol_data = all_stock_data[all_stock_data['SYMBOL'] == stock_symbol]

        # Plotting the various metrics
        plt.plot(stock_symbol_data['DATE'], stock_symbol_data['VWAP'], label=f'{stock_symbol} - VWAP', linestyle='--', marker='o')
        plt.plot(stock_symbol_data['DATE'], stock_symbol_data['HIGH'], label=f'{stock_symbol} - HIGH', linestyle='-', marker='o')
        plt.plot(stock_symbol_data['DATE'], stock_symbol_data['LOW'], label=f'{stock_symbol} - LOW', linestyle='--', marker='o')
        plt.plot(stock_symbol_data['DATE'], stock_symbol_data['OPEN'], label=f'{stock_symbol} - OPEN', linestyle='-.', marker='o')
        plt.plot(stock_symbol_data['DATE'], stock_symbol_data['CLOSE'], label=f'{stock_symbol} - CLOSE', linestyle=':', marker='o')

        # Assuming 'Volume', 'VWAP', and 'Turnover' columns are present in the dataset
        plt.bar(stock_symbol_data['DATE'], stock_symbol_data['VOLUME'], label=f'{stock_symbol} - VOLUME', alpha=0.5)
        # plt.bar(stock_symbol_data['Date'], stock_symbol_data['VWAP'], label=f'{stock_symbol} - VWAP', alpha=0.5)
        plt.bar(stock_symbol_data['DATE'], stock_symbol_data['NO OF TRADES'], label=f'{stock_symbol} - NO OF TRADES', alpha=0.5)

    plt.title(f'Stock Metrics Over Time ({time_scale} scale)')
    plt.xlabel('Date')
    plt.ylabel('Values')

    plt.xticks(rotation=45, ha = 'right')

    # Move the legend to the right of the main plot
    legend = plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    legend.set_title("Metrics")

    # Save the plot image without specifying the filename
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plot_img_data = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return plot_img_data

from ast import literal_eval  # Importing the literal_eval function to safely evaluate the string as a Python expression

@app.route('/show_previous_plot', methods=['POST', 'GET'])
def show_previous_plot():
    try:
        selected_input_index = int(request.json.get('selected_input'))

        # Read inputs from the JSON file
        with open('previous_inputs.json', 'r') as file:
            previous_inputs = [json.loads(line) for line in file]

        if 0 <= selected_input_index < len(previous_inputs):
            selected_input = previous_inputs[selected_input_index]
            stock_symbols = selected_input['stock_symbols']
            years = int(selected_input['years'])
            time_scale = selected_input['time_scale']

            all_stock_data = pd.DataFrame()
            for stock_symbol in stock_symbols:
                # Read data from the corresponding archive file
                file_path = f'archive/{stock_symbol}.csv'
                if os.path.exists(file_path):
                    stock_symbol_data = pd.read_csv(file_path)
                    stock_symbol_data.loc[:, "DATE"] = pd.to_datetime(stock_symbol_data.loc[:, "DATE"])

                    # Handle missing values if any
                    stock_symbol_data.dropna(subset=['DATE'], inplace=True)

                    # Filter data based on the time scale
                    start_date = datetime.now() - timedelta(days=years * 365)
                    stock_symbol_data = stock_symbol_data[stock_symbol_data.loc[:, "DATE"] >= start_date]

                    stock_symbol_data['Price Change'] = (stock_symbol_data['CLOSE'] - stock_symbol_data['LTP'])
                    stock_symbol_data['Gain'] = stock_symbol_data['Price Change'].apply(lambda x: x if x > 0 else 0)
                    stock_symbol_data['Loss'] = stock_symbol_data['Price Change'].apply(lambda x: -x if x < 0 else 0)

                    window_size = 0

                    # Calculate rolling window size based on time scale
                    if time_scale == 'daily':
                        window_size = years
                    elif time_scale == 'weekly':
                        window_size = years // 7
                    elif time_scale == 'monthly':
                        window_size = years // 30
                    elif time_scale == 'yearly':
                        window_size = years // 365
                    else:
                        raise ValueError('Invalid time scale selected')

                    window_size = max(1, window_size)

                    average_gain = stock_symbol_data['Gain'].rolling(window=window_size, min_periods=1).mean()
                    average_loss = stock_symbol_data['Loss'].rolling(window=window_size, min_periods=1).mean()

                    rs = average_gain / average_loss
                    stock_symbol_data['RSI'] = 100 - (100 / (1 + rs))

                    # Filtering data based on specified conditions
                    filtered_data = stock_symbol_data[(stock_symbol_data['VWAP'] > 190) & (stock_symbol_data['RSI'] > 70)]

                    all_stock_data = pd.concat([all_stock_data, filtered_data], ignore_index=True)
                else:
                    flash(f'Data file for symbol {stock_symbol} not found.')

            plot_img_data = plot_data(stock_symbols, time_scale, all_stock_data)

            # Returning the plot data as JSON
            return jsonify({'plot_image': plot_img_data})

        else:
            raise ValueError('Invalid selected input index')

    except (KeyError, ValueError, IndexError, SyntaxError) as e:
        # Print the full exception traceback for debugging
        import traceback
        traceback.print_exc()
        # Handle potential errors and provide feedback to the user
        return redirect(url_for('welcome'))


@app.route('/stock_analysis', methods=['GET', 'POST'])
def stock_analysis():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        stock_symbols = [symbol.strip() for symbol in request.form.get('symbol', '').split(',')]
        x = int(request.form['years'])
        time_scale = request.form['time_scale']
        all_stock_data = pd.DataFrame()


        # Save input to a JSON file
        with open('previous_inputs.json', 'a') as file:
            json.dump({
                'stock_symbols': stock_symbols,
                'years': x,
                'time_scale': time_scale
            }, file)
            file.write('\n')  # Add a newline for better readability



        #code to write into archieve
        start_DATE = datetime.today().date() - timedelta(days=365 * x)
        today_DATE = datetime.today().date()
        for sym in stock_symbols:
            df = stock_df(symbol = sym, from_date = start_DATE, to_date = today_DATE)
            df.to_csv(os.path.join('archive',f'{sym}.csv'), index=False)


        #here taking data from archive
        archive_folder = os.path.join(os.path.dirname(__file__), 'archive')

        if not os.path.exists(archive_folder):
            flash('Data folder not found.')
            # return redirect(url_for('index'))

        previous_inputs = session.get('previous_inputs', [])
        previous_inputs.append({
            'stock_symbols': stock_symbols,
            'years': x,
            'time_scale': time_scale
        })
        session['previous_inputs'] = previous_inputs

        for stock_symbol in stock_symbols:
            file_path = os.path.join(archive_folder, f'{stock_symbol}.csv')
            if not os.path.exists(file_path):
                flash(f'Data file for symbol {stock_symbol} not found.')
                # return redirect(url_for('index'))

            stock_data = pd.read_csv(file_path)
            if 'DATE' not in stock_data.columns:
                flash(f'Data file for symbol {stock_symbol} is missing the "Date" column.')
                # return redirect(url_for('index'))

            stock_data.loc[:,"DATE"] = pd.to_datetime(stock_data.loc[:,"DATE"])

            # Handle missing values if any
            stock_data.dropna(subset=['DATE'], inplace=True)


            if time_scale == 'daily':
                stock_data = stock_data
            elif time_scale == 'weekly':
                stock_data = stock_data.resample('W-Mon', on='DATE').last().reset_index()
            elif time_scale == 'monthly':
                stock_data = stock_data.resample('M', on='DATE').last().reset_index()
            elif time_scale == 'yearly':
                stock_data = stock_data.resample('Y', on='DATE').last().reset_index()
            else:
                flash('Invalid time scale selected')
                # return redirect(url_for('index'))


            start_date = datetime.now() - timedelta(days=x * 365)
            stock_data = stock_data[stock_data.loc[:,"DATE"] >= start_date]


            # stock_data['Average_Price'] = (stock_data['HIGH'] + stock_data['LOW']) / 2


            stock_data['Price Change'] = (stock_data['CLOSE'] - stock_data['LTP'])
            # Separate gains and losses
            stock_data['Gain'] = stock_data['Price Change'].apply(lambda x: x if x > 0 else 0)
            stock_data['Loss'] = stock_data['Price Change'].apply(lambda x: -x if x < 0 else 0)

            window_size=0

            # Calculate rolling window size based on time scale
            if time_scale == 'daily':
                window_size = x
            elif time_scale == 'weekly':
                window_size = x // 7
            elif time_scale == 'monthly':
                window_size = x // 30
            elif time_scale == 'yearly':
                window_size = x // 365
            else:
                raise ValueError('Invalid time scale selected')

            # Calculate rolling window size based on time scale
            window_size = max(1, window_size)  # Ensure window_size is at least 1


            # Calculate average gain and average loss over the specified time scale
            average_gain = stock_data['Gain'].rolling(window=window_size, min_periods=1).mean()
            average_loss = stock_data['Loss'].rolling(window=window_size, min_periods=1).mean()

            # Calculate relative strength (RS)
            rs = average_gain / average_loss

            # Calculate RSI
            stock_data['RSI'] = 100 - (100 / (1 + rs))

            filtered_data = stock_data[(stock_data['VWAP'] > 190)]
            filtered_data = stock_data[(stock_data['RSI'] > 70)]

            all_stock_data = pd.concat([all_stock_data, filtered_data], ignore_index=True)


        plot_img_data = plot_data(stock_symbols, time_scale, all_stock_data)
        return render_template('plot_stock.html', plot_image=plot_img_data)


    return render_template('plot_stock_form.html')

if __name__ == '__main__':
    app.run(debug=True)
