def get_blacklist_email_message(student_name,student_urn,blacklist_reason=None):
    """
    Returns HTML email template for blacklist notifications
    """
    reason = blacklist_reason if blacklist_reason else "not following placement guidelines"
    
    template = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Blacklist Notification</title>
    <style>
      body {{
        font-family: sans-serif;
      }}
      h1, h2, h3, p, h4 {{
        margin: 0;
      }}
      .body {{
        max-width: 24rem;
        margin-left: auto;
        margin-right: auto;
        color: #000000;
      }}
      .header {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        height: min-content;
        text-align: center;
      }}
      .header > h3 {{
        font-weight: 600;
      }}
      .container {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        background-color: #f4f4f5;
      }}
      .container > h2 {{
        font-size: 1.125rem;
        line-height: 2rem;
        font-weight: 600;
        text-align: center;
        color: #dc2626;
      }}
      .content {{
        padding-left: 1rem;
        padding-right: 1rem;
      }}
      .content > h3 {{
        margin-top: 0.5rem;
        font-size: 1rem;
        line-height: 1.75rem;
        font-weight: 600;
      }}
      .message {{
        margin-top: 1rem;
        margin-bottom: 1rem;
        line-height: 1.5;
      }}
      .footer {{
        padding-top: 1rem;
        padding-bottom: 1rem;
        font-size: 0.75rem;
        line-height: 1rem;
        text-align: center;
        color: #71717a;
      }}
      .footer > p {{
        width: 83.333333%;
        margin: 0 auto;
      }}
      .divider {{
        margin-top: 0.75rem;
        margin-bottom: 0.75rem;
        border-radius: 9999px;
        border-width: 1px;
        width: 75%;
      }}
    </style>
  </head>

  <body class="body">
    <header class="header">
      <h3>JSS</h3>
      <p>Training and Placement Cell</p>
    </header>
    <div class="container">
      <h2>Blacklist Notification</h2>

      <div class="content">
        <h3>Important Notice</h3>
        <p class="message">
          Hi {student_name}-{student_urn},<br><br>
          This is to inform you have been Blacklisted from the placement portal due to <b>{reason}<b/>. 
          Which means you will not be able to register for upcoming placement opportunities until further notice.<br><br>
          Please contact your respective Placement Secretary ( PS ) for clarification.
        </p>
      </div>
    </div>
    <footer class="footer">
      <p class="w-5/6 mx-auto">
        You have received this mail because your e-mail ID is registered with
        JSS Placement And Training Cell. This is a system-generated e-mail,
        please don't reply to this message.
      </p>
      <div class="divider"></div>
      <p>JSS Science And Technology University</p>
      <p>Mysuru Karnataka - 570006</p>
    </footer>
  </body>
</html>
    """
    return template