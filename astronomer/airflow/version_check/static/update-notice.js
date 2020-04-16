"use strict";

$(document).ready(function() {
  $(".ac-update-notice button").on("click", function() {
    var el = $(this);
    el.prop( "disabled", true );
    $.post(el.data('href')).done(() => {
      el.parents(".ac-update-notice").slideUp();
    }).fail(() => {
      alert("There was a problem submitting this request");
      el.prop( "disabled", false );
    })
  });
});
