
import mysql.connector
from mysql.connector import Error


def get_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password="Thanvir@2007",  # Enter your MySQL password
            database="library_db"
        )

        if connection.is_connected():
            print("Successfully connected to MySQL Database!")
            return connection

    except Error as e:
        print("Error while connecting to MySQL:", e)

    return None


# Test database connection
if __name__ == "__main__":
    connection = get_connection()

    if connection:
        print("Database connection successful!")

        connection.close()
        print("MySQL connection closed.")
