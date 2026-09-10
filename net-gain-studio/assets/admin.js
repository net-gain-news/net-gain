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

		// --- My Show page: audio upload, finalization countdown, abort/publish-now ---

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

		$( document ).on( 'click', '.ng-abort, .ng-publish-now', function () {
			var episodeId = $( this ).data( 'episode-id' );
			var isAbort = $( this ).hasClass( 'ng-abort' );

			ngRestPost( '/episodes/' + episodeId + '/finalize-action', { action: isAbort ? 'abort' : 'publish_now' } )
				.done( function () { ngReloadWithNotice( isAbort ? 'aborted' : 'published_now' ); } )
				.fail( ngShowError );
		} );

		// The countdown reflects server state, it isn't the source of truth for it -
		// once one reaches zero, poll that episode until the tick loop has actually
		// finalized it (the visible timer can hit zero before the next tick pass
		// runs). Each .ng-countdown element on the page runs its own independent
		// timer/poll loop.
		$( '.ng-countdown' ).each( function () {
			var $countdown = $( this );
			var episodeId  = $countdown.data( 'episode-id' );
			var remaining  = parseInt( $countdown.data( 'seconds' ), 10 ) || 0;

			var pollUntilFinalized = function () {
				$.get( ngAdmin.apiRoot + 'wp/v2/ng_episode/' + episodeId ).done( function ( episode ) {
					var state = episode.meta && episode.meta.ng_finalization ? episode.meta.ng_finalization.state : null;
					if ( 'counting_down' !== state ) {
						window.location.reload();
					} else {
						setTimeout( pollUntilFinalized, 5000 );
					}
				} );
			};

			var tick = function () {
				if ( remaining > 0 ) {
					$countdown.text( remaining );
					remaining -= 1;
					setTimeout( tick, 1000 );
					return;
				}
				$countdown.text( 'finalizing…' );
				pollUntilFinalized();
			};

			tick();
		} );
	} );
} )( jQuery );
