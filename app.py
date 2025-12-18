# app.py (root of the project)

from schedulebooker import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
