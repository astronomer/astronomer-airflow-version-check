"use strict";

$(document).ready(function() {
  $(".ac-update-notice button, .rt-eol-notice button").on("click", function() {
    var el = $(this);
    el.prop("disabled", true);
    $.post(el.data('href')).done(() => {
      el.parents(".alert").slideUp();
    }).fail(() => {
      alert("There was a problem submitting this request");
      el.prop("disabled", false);
    });
  });
});
