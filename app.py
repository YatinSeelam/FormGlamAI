# =========================
# 1. IMPORTS & FLASK SETUP
# =========================
import uuid
import urllib.parse
from flask import Flask, request, url_for, render_template, abort, Response, jsonify
import requests

app = Flask(__name__)

# =========================
# 2. IN-MEMORY DATA STORE
# =========================
form_configurations = {}

# =========================
# 3. HELPER FUNCTIONS
# =========================
def is_valid_link(link):
    """Check if the link is a valid Google Form prefill link."""
    try:
        parsed = urllib.parse.urlparse(link)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.netloc != "docs.google.com":
        return False
    if not parsed.path.startswith("/forms/d/e/"):
        return False
    if "viewform" not in parsed.path:
        return False
    return True

# =========================
# 4. MAIN ROUTES
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    """Landing page: paste the Google Form link, choose a template, and optionally customize preview colors."""
    link_value = ""
    template_choice = "modern"
    public_url = None
    form_id = None

    if request.method == "POST":
        link = request.form.get("link", "").strip()
        template_choice = request.form.get("template", "modern")
        link_value = link

        # Read custom preview color inputs (if provided)
        preview_bg = request.form.get("preview_bg", None)
        preview_text = request.form.get("preview_text", None)

        if not link or not is_valid_link(link):
            return render_template("error.html", message="Invalid Google Form prefill link.")

        parsed = urllib.parse.urlparse(link)
        modified_path = parsed.path.replace("viewform", "formResponse")
        modified_url = f"{parsed.scheme}://{parsed.netloc}{modified_path}"

        params = urllib.parse.parse_qs(parsed.query)
        fields = {}
        for key, val in params.items():
            if key.startswith("entry."):
                label = val[0] if val else "Untitled"
                fields[key] = {"label": label, "required": True}

        if not fields:
            return render_template("error.html", message="No valid form fields found in your link.")

        form_id = str(uuid.uuid4())
        form_configurations[form_id] = {
            "modified_url": modified_url,
            "fields": fields,
            "template": template_choice,
            "preview_bg": preview_bg,       # Custom background color
            "preview_text": preview_text    # Custom text color
        }

        public_url = url_for("custom_form", form_id=form_id, _external=True)
        return render_template("index.html",
                               link_value=link_value,
                               template_choice=template_choice,
                               public_url=public_url,
                               form_id=form_id)

    return render_template("index.html",
                           link_value=link_value,
                           template_choice=template_choice,
                           public_url=public_url,
                           form_id=form_id)

@app.route("/custom/<form_id>", methods=["GET"])
def custom_form(form_id):
    """Render the chosen theme template with dynamic fields."""
    config = form_configurations.get(form_id)
    if not config:
        abort(404)
    template_map = {
        "modern": "modern.html",
        "dark": "dark.html",
        "gradient": "gradient.html",
        "glassmorphism": "glassmorphism.html"
    }
    chosen_template = template_map.get(config["template"], "modern.html")
    return render_template(chosen_template, form_id=form_id, fields=config["fields"])

@app.route("/submit/<form_id>", methods=["POST"])
def submit_form(form_id):
    """Handle form submission and send data to Google Forms."""
    config = form_configurations.get(form_id)
    if not config:
        return "ERROR:Form not found"
    fields_config = config["fields"]
    modified_url = config["modified_url"]
    submitted_data = {}
    for entry_key, info in fields_config.items():
        user_value = request.form.get(entry_key, "").strip()
        if info["required"] and not user_value:
            return f"ERROR:{info['label']} is required."
        submitted_data[entry_key] = user_value
    try:
        response = requests.post(modified_url, data=submitted_data)
        print("Submitted to Google Form. Status code:", response.status_code)
    except Exception as e:
        print("Submission error:", e)
        return "ERROR:Error submitting your response. Please try again later."
    return "SUCCESS:Thank you! Your response has been submitted."

# =========================
# 5. AJAX SUBMISSION ROUTE
# =========================
@app.route("/ajax-submit/<form_id>", methods=["POST"])
def ajax_submit_form(form_id):
    """Handle AJAX submission and return JSON response."""
    config = form_configurations.get(form_id)
    if not config:
        return jsonify({"error": "Form not found"}), 404
    fields_config = config["fields"]
    modified_url = config["modified_url"]
    submitted_data = {}
    for entry_key, info in fields_config.items():
        user_value = request.form.get(entry_key, "").strip()
        if info["required"] and not user_value:
            return jsonify({"error": f"'{info['label']}' is required."}), 400
        submitted_data[entry_key] = user_value
    try:
        response = requests.post(modified_url, data=submitted_data)
        print("Submitted to Google Form. Status code:", response.status_code)
    except Exception as e:
        print("Submission error:", e)
        return jsonify({"error": "Error submitting your response. Try again later."}), 500
    return jsonify({"success": True, "message": "Thank you! Your response has been submitted."})

# =========================
# 6. EMBED SCRIPT ROUTE
# =========================
@app.route("/embed.js")
def embed_script():
    script = """
(function() {
  function loadCustomForms() {
    var divs = document.querySelectorAll('[data-customform]');
    divs.forEach(function(div) {
      var formId = div.getAttribute('data-customform');
      if (!formId) return;
      var xhr = new XMLHttpRequest();
      xhr.open('GET', '/embed/' + formId, true);
      xhr.onreadystatechange = function() {
        if (xhr.readyState == 4 && xhr.status == 200) {
          div.innerHTML = xhr.responseText;
        }
      };
      xhr.send();
    });
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    loadCustomForms();
  } else {
    document.addEventListener('DOMContentLoaded', loadCustomForms);
  }
})();
"""
    return Response(script, mimetype="application/javascript")

# =========================
# 7. EMBED FORM ROUTE
# =========================
@app.route("/embed/<form_id>")
def embed_form(form_id):
    """Return a themed HTML snippet for the live preview area using custom colors if provided."""
    config = form_configurations.get(form_id)
    if not config:
        return ""
    chosen_template = config.get("template", "modern")
    # Use custom preview colors if provided; otherwise, fallback to defaults based on theme
    preview_bg = config.get("preview_bg")
    preview_text = config.get("preview_text")
    if preview_bg and preview_text:
        outer_container_style = (
            f"width:100%; height:200%; background-color:{preview_bg}; color:{preview_text}; "
            "display:flex; justify-content:center; align-items:center;"
        )
    else:
        if chosen_template == "dark":
            outer_container_style = (
                "width:100%; height:200%; background-color:#0e0e0e; display:flex; justify-content:center; align-items:center;"
            )
        elif chosen_template == "gradient":
            outer_container_style = (
                "width:100%; height:200%; background: linear-gradient(to right, #ff7e5f, #feb47b); display:flex; justify-content:center; align-items:center;"
            )
        else:  # modern
            outer_container_style = (
                "width:100%; height:200%; background-color:#ffffff; display:flex; justify-content:center; align-items:center;"
            )

    if chosen_template == "dark":
        inner_card_style = (
            "max-width:400px; width:100%; padding:1rem; background-color:#1a1a1a; border:1px solid #444; border-radius:8px;"
        )
        button_style = "background:#4e9af1; color:#fff; padding:0.5rem 1rem; border:none; border-radius:4px;"
        label_color = "#ccc"
        input_bg = "#2b2b2b"
        input_border = "#444"
        input_text = "#fff"
    elif chosen_template == "gradient":
        inner_card_style = (
            "max-width:400px; width:100%; padding:1rem; background-color:rgba(255,255,255,0.85); border:1px solid #ccc; border-radius:8px;"
        )
        button_style = "background:#ff7e5f; color:#fff; padding:0.5rem 1rem; border:none; border-radius:4px;"
        label_color = "#333"
        input_bg = "#fff"
        input_border = "#ccc"
        input_text = "#333"
    else:  # modern
        inner_card_style = (
            "max-width:400px; width:100%; padding:1rem; background-color:#ffffff; border:1px solid #ccc; border-radius:8px;"
        )
        button_style = "background:#4e9af1; color:#fff; padding:0.5rem 1rem; border:none; border-radius:4px;"
        label_color = "#333"
        input_bg = "#fff"
        input_border = "#ccc"
        input_text = "#333"

    fields_html = ""
    for entry_key, info in config["fields"].items():
        label_text = info["label"]
        fields_html += f"""
        <div style="margin-bottom:1rem;">
          <label style="display:block; margin-bottom:0.3rem; color:{label_color}; font-weight:600;">
            {label_text}:
          </label>
          <input 
            type="text" 
            name="{entry_key}"
            style="width:100%; padding:0.5rem; background-color:{input_bg}; color:{input_text}; border:1px solid {input_border}; border-radius:4px;"
          />
        </div>
        """

    form_html = f"""
    <div style="{outer_container_style}">
      <div style="{inner_card_style}">
        <form id="ajaxForm" action="/submit/{form_id}" method="POST" style="width:100%;">
          {fields_html}
          <button type="submit" style="{button_style} width:100%;">Submit</button>
        </form>
      </div>
    </div>
    """
    return form_html

# =========================
# 8. RUN THE APP
# =========================
if __name__ == "__main__":
    app.run(debug=True, port=5001)
