document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("registerForm");
  var submitBtn = document.getElementById("registerSubmit");
  var terms = document.getElementById("kullanim_kosullari");
  if (!form || !submitBtn) return;

  var emailOk = false;
  var passwordOk = false;
  var termsOk = terms ? terms.checked : true;

  function updateSubmit() {
    submitBtn.disabled = !(emailOk && passwordOk && termsOk);
  }

  if (window.EmailValidation) {
    EmailValidation.init({
      formId: "registerForm",
      emailId: "email",
      feedbackId: "emailFeedback",
      onChange: function (ok) {
        emailOk = ok;
        updateSubmit();
      },
    });
  }

  if (window.PasswordValidation) {
    PasswordValidation.init({
      formId: "registerForm",
      passwordId: "password",
      confirmId: "password_tekrar",
      rulesId: "passwordRules",
      matchId: "passwordMatch",
      onChange: function (ok) {
        passwordOk = ok;
        updateSubmit();
      },
    });
  }

  if (terms) {
    terms.addEventListener("change", function () {
      termsOk = terms.checked;
      updateSubmit();
    });
  }

  updateSubmit();
});
