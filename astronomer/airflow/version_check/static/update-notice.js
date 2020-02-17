"use strict";

$(document).ready(function() {
  $(".cea-update-notice button").on("click", function() {
    var el = $(this);
    el.prop( "disabled", true );
    $.post(el.data('href')).done(() => {
      el.parents(".cea-update-notice").slideUp();
    }).fail(() => {
      alert("There was a problem submitting this request");
      el.prop( "disabled", false );
    })
  });
});
