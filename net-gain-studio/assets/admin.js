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

		// Script generation zone: show that zone's clock beside the picker, so a shift between daylight and standard time is visible.
		$( '#ng_script_timezone' ).on( 'change', function () {
			var zone = $( this ).val() || $( this ).data( 'site-zone' );
			var label = '';
			try {
				label = 'Now ' + new Intl.DateTimeFormat( 'en-US', { timeZone: zone, hour: 'numeric', minute: '2-digit', timeZoneName: 'short' } ).format( new Date() ) + '.';
			} catch ( err ) {}
			$( '#ng_script_tz_now' ).text( label );
		} );

		// Duotone colour fields: the native <input type="color"> swatch is a visual
		// helper only (not submitted - no name attribute) since not every browser's
		// built-in picker surfaces a hex field (Safari/macOS notably doesn't). The
		// adjacent plain text input is what actually gets saved; each keeps the
		// other in sync.
		$( document ).on( 'input', '.ng-duotone-picker', function () {
			$( this ).next( '.ng-duotone-hex' ).val( $( this ).val() );
		} );
		$( document ).on( 'input', '.ng-duotone-hex', function () {
			var value = $( this ).val();
			if ( /^#[0-9a-fA-F]{6}$/.test( value ) ) {
				$( this ).prev( '.ng-duotone-picker' ).val( value );
			}
		} );

		// --- My Show page: audio upload and replacement ---

		function ngRestPost( path, data ) {
			return $.ajax( {
				url: ngAdmin.restUrl + path,
				method: 'POST',
				beforeSend: function ( xhr ) {
					xhr.setRequestHeader( 'X-WP-Nonce', ngAdmin.nonce );
				},
				data: data,
			} );
		}

		function ngReloadWithNotice( notice ) {
			var url = new URL( window.location.href );
			url.searchParams.set( 'ng_notice', notice );
			window.location.href = url.toString();
		}

		function ngShowError( xhr ) {
			var message = ( xhr.responseJSON && xhr.responseJSON.message ) || 'Unknown error';
			alert( message );
		}

		// Event delegation + per-element data-episode-id throughout, since a talent
		// covering/hosting multiple shows can have more than one of these cards on
		// the page at once - ids would collide, so nothing here is id-addressed.
		$( document ).on( 'click', '.ng-upload-audio', function ( e ) {
			e.preventDefault();
			var episodeId = $( this ).data( 'episode-id' );

			var frame = wp.media( {
				title: 'Select or Upload Audio',
				button: { text: 'Use this file' },
				library: { type: 'audio' },
				multiple: false,
			} );

			frame.on( 'select', function () {
				var attachment = frame.state().get( 'selection' ).first().toJSON();
				ngRestPost( '/episodes/' + episodeId + '/audio', { attachment_id: attachment.id } )
					.done( function () { ngReloadWithNotice( 'audio_uploaded' ); } )
					.fail( ngShowError );
			} );

			frame.open();
		} );

		// Replace the audio of an already-recorded episode (Spec Section 8.4):
		// confirm what it will do to THIS episode (text built server-side from the
		// episode's actual state), pick the new file, then hand off to the server.
		$( document ).on( 'click', '.ng-replace-audio', function ( e ) {
			e.preventDefault();
			var episodeId = $( this ).data( 'episode-id' );
			if ( ! window.confirm( $( this ).attr( 'data-confirm' ) ) ) {
				return;
			}

			var frame = wp.media( {
				title: 'Select or Upload the Replacement Audio',
				button: { text: 'Use this file' },
				library: { type: 'audio' },
				multiple: false,
			} );

			frame.on( 'select', function () {
				var attachment = frame.state().get( 'selection' ).first().toJSON();
				ngRestPost( '/episodes/' + episodeId + '/replace-audio', { attachment_id: attachment.id } )
					.done( function () { ngReloadWithNotice( 'audio_replacement_queued' ); } )
					.fail( ngShowError );
			} );

			frame.open();
		} );

		$( document ).on( 'click', '.ng-retry-audio-replacement', function () {
			var episodeId = $( this ).data( 'episode-id' );
			ngRestPost( '/episodes/' + episodeId + '/replace-audio/retry', {} )
				.done( function () { ngReloadWithNotice( 'audio_replacement_retried' ); } )
				.fail( ngShowError );
		} );

		// Talent can regenerate their own episode's images (can_act_for_show,
		// per an explicit permission carve-out - see class-rest-show-actions.php)
		// unlike generate_script/publish_captivate, which stay admin-only.
		// force:true since this is always a deliberate re-trigger from a
		// human looking at an already-rendered result, not a routine first run.
		$( document ).on( 'click', '.ng-regenerate-images', function () {
			var showId = $( this ).data( 'show-id' );

			ngRestPost( '/shows/' + showId + '/actions', { action: 'generate_images', force: true } )
				.done( function () { ngReloadWithNotice( 'images_regenerate_queued' ); } )
				.fail( ngShowError );
		} );
	} );
} )( jQuery );
