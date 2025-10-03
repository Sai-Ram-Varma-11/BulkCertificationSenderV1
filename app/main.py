import os
import uuid
from datetime import datetime
import tempfile

from flask import Flask, request, redirect, url_for, render_template, session, flash, send_file, Response
from dotenv import load_dotenv

from .utils.db import db, init_db
from .utils.auth import password_hash, verify_password, require_roles
from .utils.cert_generator import generate_certificate_png
from .utils.emailer import send_certificate_email
from sqlalchemy import or_

load_dotenv()

app = Flask(__name__, template_folder="templates/html", static_folder="static")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///eventeye.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


class User(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(255), unique=True, nullable=False)
	password_hash = db.Column(db.String(255), nullable=False)
	role = db.Column(db.String(32), nullable=False, default="club")
	club = db.Column(db.String(128), nullable=True)


class Participant(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(255), nullable=False)
	email = db.Column(db.String(255), nullable=False)
	event = db.Column(db.String(255), nullable=False)
	date = db.Column(db.String(64), nullable=True)
	organizer = db.Column(db.String(255), nullable=True)
	unique_id = db.Column(db.String(128), unique=True, nullable=False)
	club = db.Column(db.String(128), nullable=True)
	status = db.Column(db.String(32), default="pending")


class Template(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	club = db.Column(db.String(128), nullable=True)
	name = db.Column(db.String(255), nullable=False)
	file_path = db.Column(db.String(512), nullable=False)
	coordinates_path = db.Column(db.String(512), nullable=False)


class CertificateLog(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=False)
	file_path = db.Column(db.String(512), nullable=False)
	email_status = db.Column(db.String(32), default="pending")
	created_at = db.Column(db.DateTime, default=datetime.utcnow)


@app.route("/initdb")
def route_initdb():
	with app.app_context():
		init_db(db)
		admin_email = os.getenv("SUPERADMIN_EMAIL", "admin@example.com")
		admin_pass = os.getenv("SUPERADMIN_PASSWORD", "admin123")
		user = User.query.filter_by(email=admin_email).first()
		if not user:
			user = User(email=admin_email, password_hash=password_hash(admin_pass), role="superadmin")
			db.session.add(user)
			db.session.commit()
	return "DB initialized and superadmin ensured"


@app.route("/")
@require_roles("admin", "superadmin", "club")
def index():
	club = session.get("club")
	role = session.get("role")
	# filters
	query_text = (request.args.get("q") or "").strip().lower()
	status_filter = (request.args.get("status") or "").strip().lower()
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	if query_text:
		q = q.filter(or_(Participant.name.ilike(f"%{query_text}%"), Participant.email.ilike(f"%{query_text}%")))
	if status_filter and status_filter != "all":
		q = q.filter_by(status=status_filter)
	participants = q.order_by(Participant.id.desc()).all()

	# kpis
	total = Participant.query.count() if role != "club" else Participant.query.filter_by(club=club).count()
	generated_count = (Participant.query.filter(Participant.status.in_(["generated","emailed"])) if role != "club" else Participant.query.filter_by(club=club).filter(Participant.status.in_(["generated","emailed"])) ).count()
	sent_count = (Participant.query.filter_by(status="emailed") if role != "club" else Participant.query.filter_by(club=club, status="emailed")).count()
	bounced_count = (Participant.query.filter_by(status="bounced") if role != "club" else Participant.query.filter_by(club=club, status="bounced")).count()
	deliver_base = sent_count + bounced_count
	delivery_success = int(round((sent_count / deliver_base) * 100)) if deliver_base else 0

	# templates list
	templates_q = Template.query
	if role == "club":
		templates_q = templates_q.filter(db.or_(Template.club == None, Template.club == club))
	templates = templates_q.order_by(Template.id.desc()).all()

	return render_template(
		"dashboard.html",
		participants=participants,
		total=total,
		generated_count=generated_count,
		sent_count=sent_count,
		delivery_success=delivery_success,
		bounced_count=bounced_count,
		templates=templates,
		query_text=query_text,
		status_filter=status_filter or "all",
	)


@app.route("/report.csv")
@require_roles("admin", "superadmin", "club")
def download_report():
	club = session.get("club")
	role = session.get("role")
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	rows = q.order_by(Participant.id.desc()).all()
	def generate():
		yield "Name,Email,Event,Date,Organizer,Status,UniqueID\n"
		for p in rows:
			yield f"{p.name},{p.email},{p.event},{p.date or ''},{p.organizer or ''},{p.status},{p.unique_id}\n"
	return Response(generate(), mimetype='text/csv', headers={"Content-Disposition":"attachment; filename=report.csv"})


@app.route("/login", methods=["GET", "POST"])
def login():
	if request.method == "POST":
		email = request.form.get("email", "").strip().lower()
		password = request.form.get("password", "")
		user = User.query.filter_by(email=email).first()
		if user and verify_password(password, user.password_hash):
			session["user_id"] = user.id
			session["role"] = user.role
			session["club"] = user.club
			return redirect(url_for("index"))
		flash("Invalid credentials", "error")
	return render_template("login.html")


@app.route("/logout")
def logout():
	session.clear()
	return redirect(url_for("login"))


@app.route("/participants", methods=["GET", "POST"])
@require_roles("admin", "superadmin", "club")
def participants():
	role = session.get("role")
	club = session.get("club")
	if request.method == "POST":
		data = {
			"name": request.form.get("name", "").strip(),
			"email": request.form.get("email", "").strip().lower(),
			"event": request.form.get("event", "").strip() or "",
			"date": request.form.get("date", "").strip(),
			"organizer": request.form.get("organizer", "").strip(),
		}
		if not all([data["name"], data["email"]]):
			flash("Missing required fields", "error")
			return redirect(url_for("index"))
		unique_id = str(uuid.uuid4())[:8]
		p = Participant(
			name=data["name"], email=data["email"], event=data.get("event"),
			date=data.get("date"), organizer=data.get("organizer"),
			unique_id=unique_id, club=club if role == "club" else request.form.get("club")
		)
		existing = Participant.query.filter_by(email=p.email, event=p.event, club=p.club).first()
		if existing:
			flash("Participant already exists for this event", "warning")
			return redirect(url_for("index"))
		db.session.add(p)
		db.session.commit()
		flash("Participant added", "success")
		return redirect(url_for("index"))

	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	participants = q.order_by(Participant.id.desc()).all()
	return render_template("participants.html", participants=participants)


@app.route("/upload_csv", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def upload_csv():
	file = request.files.get("file")
	role = session.get("role")
	club = session.get("club")
	if not file:
		flash("No file uploaded", "error")
		return redirect(url_for("index"))
	import csv
	import io as sysio
	stream = sysio.StringIO(file.stream.read().decode("utf-8"))
	reader = csv.DictReader(stream)
	count = 0
	for row in reader:
		name = (row.get("Name") or row.get("name") or "").strip()
		email = (row.get("Email") or row.get("email") or "").strip().lower()
		event = (row.get("Event") or row.get("event") or "").strip()
		date = (row.get("Date") or row.get("date") or "").strip()
		organizer = (row.get("Organizer") or row.get("organizer") or "").strip()
		unique_id = (row.get("UniqueID") or row.get("unique_id") or "").strip() or str(uuid.uuid4())[:8]
		if not (name and email):
			continue
		pclub = club if role == "club" else (row.get("Club") or row.get("club"))
		if Participant.query.filter_by(email=email, event=event, club=pclub).first():
			continue
		p = Participant(name=name, email=email, event=event, date=date, organizer=organizer, unique_id=unique_id, club=pclub)
		db.session.add(p)
		count += 1
	if count:
		db.session.commit()
	session["last_csv_name"] = file.filename
	flash(f"{count} participants successfully loaded from CSV: {file.filename}", "success")
	return redirect(url_for("index"))


@app.route("/generate_all", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def generate_all():
	role = session.get("role")
	club = session.get("club")
	# pick latest template if exists; else error
	template = Template.query.order_by(Template.id.desc()).first()
	if not template:
		flash("No certificate template uploaded yet", "error")
		return redirect(url_for("index"))
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	participants = q.all()
	if not participants:
		flash("No participants found", "warning")
		return redirect(url_for("index"))
	out_dir = os.path.join(app.root_path, "static", "certificates")
	os.makedirs(out_dir, exist_ok=True)
	generated = 0
	for p in participants:
		outfile = os.path.join(out_dir, f"{p.unique_id}.png")
		verify_url = request.url_root.rstrip('/') + url_for("verify") + f"?code={p.unique_id}"
		generate_certificate_png(
			template_path=template.file_path,
			coordinates_path=template.coordinates_path,
			fields={"Name": p.name, "Event": p.event or "", "Date": p.date or "", "Organizer": p.organizer or ""},
			qr_value=verify_url,
			output_path=outfile,
		)
		p.status = "generated"
		log = CertificateLog(participant_id=p.id, file_path=outfile, email_status="pending")
		db.session.add(log)
		generated += 1
	if generated:
		db.session.commit()
		flash(f"Generated {generated} certificates", "success")
	return redirect(url_for("index"))


@app.route("/send_all", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def send_all():
	role = session.get("role")
	club = session.get("club")
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	participants = q.all()
	sent = 0
	for p in participants:
		log = CertificateLog.query.filter_by(participant_id=p.id).order_by(CertificateLog.id.desc()).first()
		# Only send if we have a generated file present
		if not log or not os.path.exists(log.file_path):
			continue
		ok = send_certificate_email(
			to_email=p.email,
			subject=f"Your Certificate for {p.event}",
			body=f"Hello {p.name},\n\nPlease find attached your certificate for {p.event}.\n\nRegards,\nEventEye",
			attachment_path=log.file_path,
		)
		log.email_status = "sent" if ok else "bounced"
		p.status = "emailed" if ok else "bounced"
		if ok:
			sent += 1
	db.session.commit()
	flash(f"Emails sent: {sent}", "success")
	return redirect(url_for("index"))


@app.route("/templates", methods=["GET", "POST"]) 
@require_roles("admin", "superadmin")
def manage_templates():
	if request.method == "POST":
		club = request.form.get("club") or None
		name = request.form.get("name", "").strip()
		file = request.files.get("file")
		coords = request.files.get("coordinates")
		if not (name and file and coords):
			flash("Missing fields", "error")
			return redirect(url_for("manage_templates"))
		upload_dir = os.path.join(app.root_path, "templates", "cert")
		os.makedirs(upload_dir, exist_ok=True)
		file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{file.filename}")
		file.save(file_path)
		coord_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{coords.filename}")
		coords.save(coord_path)
		t = Template(club=club, name=name, file_path=file_path, coordinates_path=coord_path)
		db.session.add(t)
		db.session.commit()
		flash("Template uploaded", "success")
		return redirect(url_for("manage_templates"))
	templates = Template.query.order_by(Template.id.desc()).all()
	return render_template("templates.html", templates=templates)


@app.route("/generate", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def generate_batch():
	role = session.get("role")
	club = session.get("club")
	template_id = request.form.get("template_id")
	selected_ids = request.form.getlist("participant_id")
	if not template_id:
		flash("Select a template", "error")
		return redirect(url_for("index"))
	if not selected_ids:
		flash("No participants selected", "warning")
		return redirect(url_for("index"))
	template = Template.query.get(template_id)
	if not template:
		flash("Template not found", "error")
		return redirect(url_for("index"))
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	q = q.filter(Participant.id.in_(selected_ids))
	participants = q.all()
	out_dir = os.path.join(app.root_path, "static", "certificates")
	os.makedirs(out_dir, exist_ok=True)
	generated = 0
	for p in participants:
		outfile = os.path.join(out_dir, f"{p.unique_id}.png")
		verify_url = request.url_root.rstrip('/') + url_for("verify") + f"?code={p.unique_id}"
		generate_certificate_png(
			template_path=template.file_path,
			coordinates_path=template.coordinates_path,
			fields={
				"Name": p.name,
				"Event": p.event or "",
				"Date": p.date or "",
				"Organizer": p.organizer or "",
			},
			qr_value=verify_url,
			output_path=outfile,
		)
		p.status = "generated"
		log = CertificateLog(participant_id=p.id, file_path=outfile, email_status="pending")
		db.session.add(log)
		generated += 1
	if generated:
		db.session.commit()
		flash(f"Generated {generated} certificates", "success")
	else:
		flash("No participants to generate", "warning")
	return redirect(url_for("index"))


@app.route("/send_emails", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def send_emails():
	role = session.get("role")
	club = session.get("club")
	selected_ids = request.form.getlist("participant_id")
	if not selected_ids:
		flash("No participants selected", "warning")
		return redirect(url_for("index"))
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	q = q.filter(Participant.id.in_(selected_ids))
	participants = q.all()
	sent = 0
	for p in participants:
		log = CertificateLog.query.filter_by(participant_id=p.id).order_by(CertificateLog.id.desc()).first()
		if not log or not os.path.exists(log.file_path):
			continue
		subject = f"Your Certificate for {p.event}"
		body = f"Hello {p.name},\n\nPlease find attached your certificate for {p.event}.\n\nRegards,\nEventEye"
		ok = send_certificate_email(to_email=p.email, subject=subject, body=body, attachment_path=log.file_path)
		log.email_status = "sent" if ok else "bounced"
		p.status = "emailed" if ok else "bounced"
		if ok:
			sent += 1
	db.session.commit()
	flash(f"Emails sent: {sent}", "success")
	return redirect(url_for("index"))


@app.route("/certificate/<code>")
@require_roles("admin", "superadmin", "club")
def certificate_view(code: str):
	p = Participant.query.filter_by(unique_id=code).first()
	if not p:
		flash("Certificate not found", "error")
		return redirect(url_for("index"))
	log = CertificateLog.query.filter_by(participant_id=p.id).order_by(CertificateLog.id.desc()).first()
	if not log:
		flash("Certificate not generated yet", "warning")
		return redirect(url_for("index"))
	return send_file(log.file_path, as_attachment=False)


@app.route("/verify")
def verify():
	code = request.args.get("code")
	if not code:
		return render_template("verify.html", ok=False, message="Missing code")
	p = Participant.query.filter_by(unique_id=code).first()
	if not p:
		return render_template("verify.html", ok=False, message="Certificate not found")
	return render_template("verify.html", ok=True, participant=p)


@app.route("/users", methods=["GET", "POST"]) 
@require_roles("superadmin", "admin")
def users():
	if request.method == "POST":
		email = request.form.get("email", "").strip().lower()
		password = request.form.get("password", "")
		role = request.form.get("role", "club")
		club = request.form.get("club") or None
		if not (email and password and role):
			flash("Missing fields", "error")
			return redirect(url_for("users"))
		if User.query.filter_by(email=email).first():
			flash("Email already exists", "error")
			return redirect(url_for("users"))
		u = User(email=email, password_hash=password_hash(password), role=role, club=club)
		db.session.add(u)
		db.session.commit()
		flash("User created", "success")
		return redirect(url_for("users"))
	users = User.query.order_by(User.id.desc()).all()
	return render_template("users.html", users=users)


@app.route("/download_preview", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def download_preview():
	event_name = request.form.get("event_name", "").strip() or "Awesome Hackathon"
	date = request.form.get("date", "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
	organizer = request.form.get("organizer", "").strip() or "EventEye Org"
	name = request.form.get("name", "").strip() or "Preview Recipient"
	bg = request.files.get("bg_image")
	if not bg:
		flash("Please choose a background image", "warning")
		return redirect(url_for("index"))
	# Save background to temp file
	tmp_dir = os.path.join(app.static_folder, "tmp")
	os.makedirs(tmp_dir, exist_ok=True)
	bg_path = os.path.join(tmp_dir, f"bg_{uuid.uuid4()}.png")
	bg.save(bg_path)
	# Use default coordinates.json in project root if no template coords
	coords_path = os.path.join(os.path.dirname(app.root_path), "coordinates.json")
	if not os.path.exists(coords_path):
		coords_path = os.path.join(app.root_path, "..", "coordinates.json")
		coords_path = os.path.abspath(coords_path)
	out_path = os.path.join(tmp_dir, f"preview_{uuid.uuid4()}.png")
	generate_certificate_png(
		template_path=bg_path,
		coordinates_path=coords_path,
		fields={"Name": name, "Event": event_name, "Date": date, "Organizer": organizer},
		qr_value=None,
		output_path=out_path,
	)
	return send_file(out_path, as_attachment=True, download_name="certificate_preview.png")


@app.route("/participants/remove/<int:pid>", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def participant_remove(pid: int):
	role = session.get("role")
	club = session.get("club")
	p = Participant.query.get(pid)
	if not p or (role == "club" and p.club != club):
		flash("Participant not found", "error")
		return redirect(url_for("index"))
	CertificateLog.query.filter_by(participant_id=p.id).delete()
	db.session.delete(p)
	db.session.commit()
	flash("Participant removed", "success")
	return redirect(url_for("index"))


@app.route("/participants/remove_all", methods=["POST"]) 
@require_roles("admin", "superadmin", "club")
def participant_remove_all():
	role = session.get("role")
	club = session.get("club")
	q = Participant.query
	if role == "club":
		q = q.filter_by(club=club)
	rows = q.all()
	ids = [r.id for r in rows]
	CertificateLog.query.filter(CertificateLog.participant_id.in_(ids)).delete(synchronize_session=False)
	for r in rows:
		db.session.delete(r)
	db.session.commit()
	flash("All participants removed", "success")
	return redirect(url_for("index"))




if __name__ == "__main__":
	with app.app_context():
		init_db(db)
	app.run(debug=True)
