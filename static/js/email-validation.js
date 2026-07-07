(function () {
  var EMAIL_PATTERN = /^[\w.+-]+@[\w-]+\.[\w.-]+$/;

  function isValidEmail(value) {
    var email = (value || "").trim().toLowerCase();
    if (!email) return false;
    return EMAIL_PATTERN.test(email);
  }

  window.EmailValidation = {
    isValid: isValidEmail,

    init: function (options) {
      options = options || {};
      var emailEl = document.getElementById(options.emailId || "email");
      var feedbackEl = document.getElementById(options.feedbackId || "emailFeedback");
      var formEl = options.formId ? document.getElementById(options.formId) : null;

      if (!emailEl) return;

      function update() {
        var value = emailEl.value.trim();
        var ok = isValidEmail(value);

        if (!feedbackEl) {
          if (typeof options.onChange === "function") {
            options.onChange(ok, value);
          }
          return ok;
        }

        if (!value) {
          feedbackEl.textContent = "";
          feedbackEl.className = "email-feedback small mt-2 text-muted";
          emailEl.classList.remove("is-valid", "is-invalid");
        } else if (ok) {
          feedbackEl.textContent = "Geçerli e-posta formatı.";
          feedbackEl.className = "email-feedback small mt-2 text-success";
          emailEl.classList.add("is-valid");
          emailEl.classList.remove("is-invalid");
        } else {
          feedbackEl.textContent = "Geçerli bir e-posta girin (ör. ad@ornek.com).";
          feedbackEl.className = "email-feedback small mt-2 text-danger";
          emailEl.classList.add("is-invalid");
          emailEl.classList.remove("is-valid");
        }

        if (typeof options.onChange === "function") {
          options.onChange(ok, value);
        }
        return ok;
      }

      emailEl.addEventListener("input", update);
      emailEl.addEventListener("blur", function () {
        emailEl.value = emailEl.value.trim().toLowerCase();
        update();
      });

      if (formEl) {
        formEl.addEventListener("submit", function (e) {
          emailEl.value = emailEl.value.trim().toLowerCase();
          if (!update()) {
            e.preventDefault();
            emailEl.focus();
          }
        });
      }

      update();
    },
  };
})();
