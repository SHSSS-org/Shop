# SHSSS Marketplace

A web application for boarding house students to buy and sell items safely within their community.

## Features

- **Marketplace**: Browse all approved items for sale
- **List Items**: Submit items for sale (requires admin approval)
- **Admin Panel**: Approve, edit, or delete listings
- **Rate Limiting**: Limits users to 10 listings per day per IP address

## Setup Instructions

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python app.py`
4. Access the application at `http://localhost:5000`

## Admin Access

- Username: `admin`
- Password: `admin123`

## Deployment on Render

1. Connect your GitHub repository to Render
2. Set the build command to `pip install -r requirements.txt`
3. Set the start command to `python app.py`
4. Deploy!

## Database

The application uses SQLite for data storage. The database file `marketplace.db` will be created automatically on first run.

## API Endpoints

- `GET /api/products` - Get all approved products
- `POST /api/products` - Submit a new product listing
- `POST /api/admin/login` - Admin authentication
- `GET /api/admin/products` - Get products by status (admin only)
- `PUT /api/admin/products/<id>` - Update product status (admin only)
- `DELETE /api/admin/products/<id>` - Delete a product (admin only)
