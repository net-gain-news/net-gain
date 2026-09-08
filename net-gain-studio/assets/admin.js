/* global wp, jQuery */
( function ( $ ) {
	'use strict';

	$( function () {
		// Branding frame pickers (wp.media - WordPress core, no build step needed).
		$( '.ng-frame-select' ).on( 'click', function ( e ) {
			e.preventDefault();
			var $picker  = $( this ).closest( '.ng-frame-picker' );
			var $input   = $picker.find( '.ng-frame-input' );
			var $preview = $picker.find( '.ng-frame-preview' );

			var frame = wp.media( {
				title: 'Select Frame Image',
				button: { text: 'Use this image' },
				library: { type: 'image' },
				multiple: false,
			} );

			frame.on( 'select', function () {
				var attachment = frame.state().get( 'selection' ).first().toJSON();
				$input.val( attachment.id );
				var thumb = attachment.sizes && attachment.sizes.thumbnail ? attachment.sizes.thumbnail.url : attachment.url;
				$preview.html( '<img src="' + thumb + '" style="max-width:100px;max-height:100px;">' );
			} );

			frame.open();
		} );

		// Publish time/timezone fields only make sense in scheduled mode.
		$( '.ng-publish-mode' ).on( 'change', function () {
			var scheduled = $( '.ng-publish-mode:checked' ).val() === 'scheduled';
			$( '.ng-publish-schedule-row' ).toggle( scheduled );
		} );
	} );
} )( jQuery );
