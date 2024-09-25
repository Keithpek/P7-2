from flask import Flask, request, jsonify
from flask_cors import CORS
# Import main program as module here then call function below
from main import main
import json

app = Flask(__name__)
CORS(app)  # Cross-Origin Resource Sharing, to allow HTML to send values here

# Path to config.json to change parameters
json_file_path = 'config.json'


def update_search_queries(title, location):
    try:
        # Open and load current json data
        with open(json_file_path, 'r') as file:
            data = json.load(file)

        # Check if theres is an entry to replace in search_queries
        query_replaced = False
        for query in data['search_queries']:
            if query['keywords'] == title or query['location'] == location:
                # Replace keywords and location
                query['keywords'] = title
                query['location'] = location
                query_replaced = True
                break

        # If no entry found, replace the first entry
        if not query_replaced and data['search_queries']:
            data['search_queries'][0]['keywords'] = title
            data['search_queries'][0]['location'] = location
            query_replaced = True

        # save updated data back to json file
        with open(json_file_path, 'w') as file:
            json.dump(data, file, indent=4)  # pretty-print with indent

        if query_replaced:
            return f"Search queries replaced with new data: {title}, {location}"
        else:
            return "No search queries found to replace"

    except Exception as e:
        return f"An error occurred: {str(e)}"


# Define route to handle form submission
@app.route('/submit_form', methods=['POST'])
def submit_form():
    # Get data from JS POST request
    data = request.json
    title = data.get('title')
    location = data.get('location')

    # update search queries in json file with new data
    result = update_search_queries(title, location)

    # Run main program after updating config.json
    main_program = main(json_file_path)

    # Return response to front-end
    return jsonify({
        "message": result,
        "title": title,
        "location": location,
        "main_program": main_program
    })


# Run app
if __name__ == '__main__':
    app.run(debug=True)