<?php
/**
 * /{show-slug}/latest/ (e.g. /edtech/latest/) sends the visitor to that show's newest published episode page, and
 * /latest/ sends them to the newest published episode of ANY show (the founder's email signature points there, so it
 * follows whichever show published last).
 *
 * It gives anything that cannot change daily (the founder's email signature, a pinned social post) one fixed address
 * for "today's newscast". A temporary redirect that is never cached or indexed, so the destination follows the newest
 * episode and search engines treat the episode page itself, not this address, as the page. A "?autoplay=1" on the
 * request is carried through, because the signature's newscast line draws a Listen button and pressing it should play.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Latest_Redirect {

	public static function register() {
		add_action( 'parse_request', array( __CLASS__, 'maybe_redirect' ), 1 );
	}

	/** Pure: 'edtech/latest' -> 'edtech'; '' for any other path. */
	public static function show_slug( $path ) {
		return preg_match( '#^([a-z0-9][a-z0-9-]*)/latest$#', trim( (string) $path, '/' ), $m ) ? $m[1] : '';
	}

	/** Pure: true for the network-wide address, '/latest/'. */
	public static function is_network_path( $path ) {
		return 'latest' === trim( (string) $path, '/' );
	}

	/**
	 * The newest published episode post: of one show when $term_id is given, otherwise of any show. The email-signature
	 * image uses this same query to decide whether a show's episode is the network's newest, so the image and the
	 * address it links to can never disagree.
	 */
	public static function newest_episode( $term_id = 0 ) {
		$args = array(
			'post_type'      => 'podcast',
			'post_status'    => 'publish',
			'posts_per_page' => 1,
			'orderby'        => 'date',
			'order'          => 'DESC',
		);
		if ( $term_id ) {
			$args['tax_query'] = array( array( 'taxonomy' => 'series', 'field' => 'term_id', 'terms' => (int) $term_id ) );
		}
		$posts = get_posts( $args );
		return empty( $posts ) ? null : $posts[0];
	}

	/** Pure: the destination, carrying autoplay through only when the request asked for exactly autoplay=1. */
	public static function destination( $permalink, $autoplay_param ) {
		return '1' === (string) $autoplay_param ? add_query_arg( 'autoplay', '1', $permalink ) : $permalink;
	}

	public static function maybe_redirect( $wp = null ) {
		$path = isset( $wp->request ) ? (string) $wp->request : '';
		if ( '' === $path && isset( $_SERVER['REQUEST_URI'] ) ) {
			$path = (string) wp_parse_url( wp_unslash( $_SERVER['REQUEST_URI'] ), PHP_URL_PATH ); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		}
		$network = self::is_network_path( $path );
		$slug    = $network ? '' : self::show_slug( $path );
		if ( ! $network && '' === $slug ) {
			return;
		}
		if ( $network ) {
			$post = self::newest_episode();
		} else {
			$term = get_term_by( 'slug', $slug, 'series' );
			if ( ! $term ) {
				return;    // not a show: normal 404 handling
			}
			$post = self::newest_episode( $term->term_id );
		}
		if ( ! $post ) {
			return;
		}

		$autoplay = isset( $_GET['autoplay'] ) ? sanitize_text_field( wp_unslash( $_GET['autoplay'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification
		header( 'Cache-Control: no-store, no-cache, must-revalidate, max-age=0' );
		header( 'X-Robots-Tag: noindex' );
		wp_redirect( self::destination( get_permalink( $post ), $autoplay ), 302 ); // phpcs:ignore WordPress.Security.SafeRedirect -- the site's own episode permalink
		exit;
	}
}
