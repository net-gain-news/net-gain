( function () {
	// Kit's sign-up script fires this event, with the address, just before it sends the visitor on to the welcome page.
	document.addEventListener( 'ckjs:submission:complete', function ( e ) {
		try {
			var address = e && e.detail && e.detail.email_address;
			if ( address ) {
				window.sessionStorage.setItem( 'ngSignup', JSON.stringify( { e: String( address ), t: Date.now() } ) );
			}
		} catch ( err ) {}
	} );
} )();
