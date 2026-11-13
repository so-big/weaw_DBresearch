An webapp database for stored Contracts and research project grants, used for Department.
My assignment are design database system.
### System design
Simply the core idea is a Cloud storage For private document *mostly are scanned PDF files*, but balance with easy use for user experience and A robust backend system.
- **Data storage**: The server will store data and encrypted them
- **Document info and tags**: mostly document are pdf file with likely same pattern, so should have system that help auto fill like Main title, Owner, time&date, other let user complete and double check.
- **Upload and Download**: user and upload file and download them, and have temporary document share, can config time expire *default 24h*, public access or password *with auto code gen* 
- **Search and filter**: can search with anything like owner name, title and can filter with tags like is what categories.
- **Login system**: create an simple login system, this part are not important yet because my task are just design the database system. 
- **Roles**: 3 role 
	- ADMIN: Can manage account and see the what many link are sharing now, and can manage them.
	- USER: Can upload and download the document, for employee
	- GUESS: can't see anything, needed to access via shared document
### Frontend design
Focus on ux/ui, seamless and work on most device PC/Table and phone low-end to high-end.
there are two part External funding and Internal funding, about how document look like, i will provide later.