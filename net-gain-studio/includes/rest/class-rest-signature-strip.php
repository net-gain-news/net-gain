<?php
/**
 * POST /net-gain/v1/shows/{id}/signature-strip - written by tick.py (pipeline/signature_strip.py) after each website
 * publish. Stores the two colourways (light, dark) of the founder's email-signature "latest newscast" image as plain
 * files at fixed URLs under uploads/ng-signature/, so a signature that points at them always shows the newest
 * newscast without any change to the signature itself.
 *
 *   {uploads}/ng-signature/{show-slug}-strip-light.png
 *   {uploads}/ng-signature/{show-slug}-strip-dark.png

 * (The earlier 512x40 files, {show-slug}-newscast-{light,dark}.png, are left as they were: signatures sent before the
 * 340 px redesign size their image at 512x40 and would show a squashed strip if that file changed shape.)
 *
 * The images are SERVED from /ng-signature/{show-slug}-strip-{light,dark}.png (not from the uploads URL): the host's
 * web server hands real files out with a Last-Modified header and no cache directive, so every cache (Apple Mail's image
 * proxy kept the strip for a whole day, 2026-10-19) invents its own lifetime. The route answers with "revalidate every
 * time" headers, an ETag and 304s, which is the most a signature can ask of a cache.
 *
 * An episode older than the one already shown is ignored, so republishing or re-running an old day never rolls the
 * signature backwards. Files are validated as real PNGs of a sane size and written atomically.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Signature_Strip {

	const DIR       = 'ng-signature';
	const MAX_BYTES = 262144;
	const MAX_WIDTH = 3200;

	const IMAGE_PATTERN = '#^ng-signature/([a-z0-9][a-z0-9-]*)-strip-(light|dark)\.png$#';

	/** Serves the stored image at a path no real file occupies, so the request reaches WordPress and can carry cache headers. */
	public static function register() {
		add_action( 'parse_request', array( __CLASS__, 'maybe_serve_image' ), 1 );
	}

	/** Pure: 'ng-signature/edtech-strip-dark.png' -> array( 'edtech', 'dark' ), or null. */
	public static function image_request( $path ) {
		return preg_match( self::IMAGE_PATTERN, trim( (string) $path, '/' ), $m ) ? array( $m[1], $m[2] ) : null;
	}

	/** Pure: the validators for a file's size and modification time. */
	public static function validators( $size, $mtime ) {
		return array(
			'etag'          => '"' . md5( $size . '|' . $mtime ) . '"',
			'last_modified' => gmdate( 'D, d M Y H:i:s', (int) $mtime ) . ' GMT',
		);
	}

	/** Pure: true when the request's validators say the client already holds this exact file. */
	public static function is_not_modified( $if_none_match, $if_modified_since, $etag, $mtime ) {
		if ( '' !== (string) $if_none_match ) {
			return in_array( $etag, array_map( 'trim', explode( ',', (string) $if_none_match ) ), true );
		}
		$since = '' !== (string) $if_modified_since ? strtotime( (string) $if_modified_since ) : false;
		return false !== $since && (int) $mtime <= $since;
	}

	public static function maybe_serve_image( $wp = null ) {
		$path = isset( $wp->request ) ? (string) $wp->request : '';
		if ( '' === $path && isset( $_SERVER['REQUEST_URI'] ) ) {
			$path = (string) wp_parse_url( wp_unslash( $_SERVER['REQUEST_URI'] ), PHP_URL_PATH ); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		}
		$match = self::image_request( $path );
		if ( null === $match ) {
			return;
		}
		$file = trailingslashit( wp_upload_dir()['basedir'] ) . self::DIR . "/{$match[0]}-strip-{$match[1]}.png";
		if ( ! is_file( $file ) ) {
			return;    // normal 404 handling
		}

		$size = (int) filesize( $file );
		$v    = self::validators( $size, filemtime( $file ) );
		header( 'Content-Type: image/png' );
		header( 'Cache-Control: no-cache, max-age=0, must-revalidate' );
		header( 'ETag: ' . $v['etag'] );
		header( 'Last-Modified: ' . $v['last_modified'] );
		header( 'X-Robots-Tag: noindex' );
		if ( self::is_not_modified( $_SERVER['HTTP_IF_NONE_MATCH'] ?? '', $_SERVER['HTTP_IF_MODIFIED_SINCE'] ?? '', $v['etag'], filemtime( $file ) ) ) { // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
			status_header( 304 );
			exit;
		}
		status_header( 200 );
		header( 'Content-Length: ' . $size );
		if ( isset( $_SERVER['REQUEST_METHOD'] ) && 'HEAD' !== $_SERVER['REQUEST_METHOD'] ) {
			readfile( $file );
		}
		exit;
	}

	public function register_routes() {
		register_rest_route(
			'net-gain/v1',
			'/shows/(?P<id>\d+)/signature-strip',
			array(
				'methods'             => 'POST',
				'callback'            => array( $this, 'store' ),
				'permission_callback' => function ( WP_REST_Request $request ) {
					return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
				},
			)
		);
	}

	/** Pure: base64 text -> PNG bytes, or null when it is not a PNG of acceptable size. */
	public static function decode_png( $b64 ) {
		if ( ! is_string( $b64 ) || '' === $b64 ) {
			return null;
		}
		$bytes = base64_decode( $b64, true );
		if ( false === $bytes || strlen( $bytes ) > self::MAX_BYTES || 0 !== strpos( $bytes, "\x89PNG\r\n\x1a\n" ) ) {
			return null;
		}
		$info = @getimagesizefromstring( $bytes );
		if ( ! $info || IMAGETYPE_PNG !== $info[2] || $info[0] > self::MAX_WIDTH || $info[1] > self::MAX_WIDTH ) {
			return null;
		}
		return $bytes;
	}

	/** Pure: true when $date (Y-m-d) is older than the date already stored. */
	public static function is_older( $date, $stored ) {
		return '' !== (string) $stored && strcmp( (string) $date, (string) $stored ) < 0;
	}

	public function store( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$show    = get_post( $show_id );
		if ( ! $show || Net_Gain_CPT_Show::POST_TYPE !== $show->post_type ) {
			return new WP_Error( 'ng_show_not_found', 'Show not found.', array( 'status' => 404 ) );
		}

		$date = (string) $request->get_param( 'episode_date' );
		if ( ! preg_match( '/^\d{4}-\d{2}-\d{2}$/', $date ) ) {
			return new WP_Error( 'ng_bad_request', 'episode_date must be YYYY-MM-DD.', array( 'status' => 400 ) );
		}

		$light = self::decode_png( $request->get_param( 'light_png' ) );
		$dark  = self::decode_png( $request->get_param( 'dark_png' ) );
		if ( null === $light || null === $dark ) {
			return new WP_Error( 'ng_bad_image', 'Both images must be PNG files of acceptable size.', array( 'status' => 400 ) );
		}

		if ( self::is_older( $date, get_post_meta( $show_id, 'ng_signature_strip_date', true ) ) ) {
			return rest_ensure_response( array( 'status' => 'ignored_older' ) );
		}

		$slug = sanitize_file_name( $show->post_name );
		$dir  = trailingslashit( wp_upload_dir()['basedir'] ) . self::DIR;
		if ( ! wp_mkdir_p( $dir ) ) {
			return new WP_Error( 'ng_storage', 'Could not create the storage folder.', array( 'status' => 500 ) );
		}
		if ( ! file_exists( $dir . '/index.html' ) ) {
			file_put_contents( $dir . '/index.html', '' );
		}

		$urls = array();
		foreach ( array( 'light' => $light, 'dark' => $dark ) as $theme => $bytes ) {
			$name = "{$slug}-strip-{$theme}.png";
			$tmp  = $dir . '/.' . $name . '.tmp';
			if ( false === file_put_contents( $tmp, $bytes ) || ! rename( $tmp, $dir . '/' . $name ) ) {
				return new WP_Error( 'ng_storage', 'Could not write the image.', array( 'status' => 500 ) );
			}
			$urls[ $theme ] = home_url( '/' . self::DIR . '/' . $name );
		}

		update_post_meta( $show_id, 'ng_signature_strip_date', $date );
		return rest_ensure_response( array( 'status' => 'stored', 'urls' => $urls ) );
	}
}
