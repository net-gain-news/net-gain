<?php
/**
 * What the public site exposes (2026-10-10, "before lifting the crawl block" audit).
 *
 *  1. Internal records are not public. The ng_show / ng_episode / ng_vertical post types are not viewable pages, but
 *     WordPress still serves published ones to anyone at /wp-json/wp/v2/ng_*, and the episode meta carried the draft
 *     script, step history and show configuration. Anonymous visitors now get a 401 for those routes and for the user
 *     list (which also named the admin and the service account). Logged-in requests - the pipeline's Application
 *     Password and the admin screens - are unaffected.
 *  2. Only anchors have public pages. Every WordPress user has an author URL; an account that is not an anchor (the
 *     admin, the service account) answers 404 there, and `?author=N` no longer redirects to it, so a username is never
 *     revealed. An anchor is a user with the talent role, a show assignment, or at least one published episode.
 *     Nothing links to these URLs (the REST user list, the author redirect and the sitemaps were the only places that
 *     did); a bot can still guess one, and gets a 404.
 *  3. The podcast plugin's own archive (/podcast/, and its older /ssp-podcast-archive/ page) renders the newest episode
 *     under a second URL, so it is a duplicate; both 301 to the episode list instead of being left to search engines.
 *     The plugin also answers every episode at /podcast/<slug>/ (its own, unprefixed URL) alongside the show URL
 *     /<show>/<slug>/ that the site links to; the former 301s to the latter (2026-10-30, after Search Console listed both).
 *  4. Comments and pings are closed everywhere, always: the site has no use for them, an open comment form is a spam
 *     surface on every episode, and the pipeline creates new posts that would otherwise inherit WordPress's "open" default.
 *  5. The REST discovery pointers (the <link rel="https://api.w.org/"> tag and Link header) are dropped from public pages.
 *  6. One podcast feed, and it is Captivate's (2026-10-12). Seriously Simple Podcasting serves its own podcast feed
 *     (/feed/podcast/<show>/, ?feed=podcast, and the series feed variants) with the same audio enclosures, and advertised
 *     it in every page's <head>. A second feed for the same show lets a directory or app pick the wrong one, so no feed
 *     link is advertised any more, and every request for the plugin's feed 301s to the show's Captivate feed (or answers
 *     410 for a show that has none). Kit's email feed (ng-email) is a different feed and is not touched.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Public_Surface {

	const PRIVATE_ROUTES   = '#^/wp/v2/(ng_episode|ng_show|ng_vertical|users)(/|$)#';
	const DUPLICATE_ARCHIVE = '#^/?(podcast|ssp-podcast-archive)(/page/\d+)?/?$#';
	const DUPLICATE_EPISODE = '#^/?podcast/[^/]+/?$#';

	/** Show slug => the feed listeners add to their podcast apps. Filterable: net_gain_podcast_feeds. */
	const PODCAST_FEEDS = array( 'edtech' => 'https://feeds.captivate.fm/netgain-edtech/' );

	public static function register() {
		add_filter( 'rest_pre_dispatch', array( __CLASS__, 'guard_rest' ), 5, 3 );
		add_action( 'template_redirect', array( __CLASS__, 'maybe_404_author' ), 1 );
		add_action( 'template_redirect', array( __CLASS__, 'redirect_duplicate_archive' ), 0 );
		add_action( 'template_redirect', array( __CLASS__, 'redirect_duplicate_episode' ), 1 );
		add_filter( 'comments_open', '__return_false', 99 );
		add_filter( 'pings_open', '__return_false', 99 );
		add_filter( 'feed_links_show_comments_feed', '__return_false' );
		add_filter( 'wp_headers', array( __CLASS__, 'drop_pingback_header' ) );
		remove_action( 'wp_head', 'rest_output_link_wp_head', 10 );
		remove_action( 'template_redirect', 'rest_output_link_header', 11 );

		add_action( 'init', array( __CLASS__, 'redirect_podcast_feed_query' ), 1 );
		add_action( 'parse_request', array( __CLASS__, 'redirect_podcast_feed' ), 1 );
		add_filter( 'ssp_show_global_feed_tag', '__return_false' );
		add_filter( 'ssp_show_series_feed_tag', '__return_false' );
		add_filter( 'ssp_rss_meta_tag', '__return_empty_string' );
		remove_action( 'wp_head', 'feed_links', 2 );
		remove_action( 'wp_head', 'feed_links_extra', 3 );
	}

	/** Pure: the Captivate feed for a show slug; an empty slug means the only show when there is exactly one. */
	public static function podcast_feed_target( $series_slug, array $feeds ) {
		$series_slug = trim( (string) $series_slug );
		if ( '' !== $series_slug ) {
			return isset( $feeds[ $series_slug ] ) ? $feeds[ $series_slug ] : null;
		}
		return 1 === count( $feeds ) ? reset( $feeds ) : null;
	}

	/** The query-string forms (?feed=podcast, ?feed=podcast&podcast_series=x) are answered by the plugin on `init`, before
	 *  WordPress parses the request, so they are caught here, first. The pretty URLs are caught in redirect_podcast_feed(). */
	public static function redirect_podcast_feed_query() {
		if ( empty( $_GET['feed'] ) || apply_filters( 'ssp_feed_slug', 'podcast' ) !== $_GET['feed'] ) { // phpcs:ignore WordPress.Security.NonceVerification
			return;
		}

		$slug = '';
		foreach ( array( 'podcast_series', 'series' ) as $key ) {
			if ( ! empty( $_GET[ $key ] ) && is_string( $_GET[ $key ] ) ) { // phpcs:ignore WordPress.Security.NonceVerification
				$slug = sanitize_title( wp_unslash( $_GET[ $key ] ) ); // phpcs:ignore WordPress.Security.NonceVerification
				break;
			}
		}
		self::answer_podcast_feed( $slug );
	}

	/** Every other request for the plugin's own podcast feed ends here, before the plugin builds anything. */
	public static function redirect_podcast_feed( $wp ) {
		$vars = isset( $wp->query_vars ) ? (array) $wp->query_vars : array();
		if ( empty( $vars['feed'] ) || apply_filters( 'ssp_feed_slug', 'podcast' ) !== $vars['feed'] ) {
			return;
		}

		$slug = '';
		foreach ( array( 'podcast_series', 'series' ) as $key ) {
			if ( ! empty( $vars[ $key ] ) ) {
				$slug = (string) $vars[ $key ];
				break;
			}
		}
		self::answer_podcast_feed( $slug );
	}

	private static function answer_podcast_feed( $slug ) {
		$target = self::podcast_feed_target( $slug, (array) apply_filters( 'net_gain_podcast_feeds', self::PODCAST_FEEDS ) );
		header( 'X-Robots-Tag: noindex' );
		if ( $target ) {
			wp_redirect( $target, 301, 'Net Gain Studio' ); // phpcs:ignore WordPress.Security.SafeRedirect -- the Captivate feed is an external URL on purpose
			exit;
		}

		status_header( 410 );
		nocache_headers();
		exit;
	}

	public static function drop_pingback_header( $headers ) {
		unset( $headers['X-Pingback'] );
		return $headers;
	}

	/** Pure: is this request path one of the podcast plugin's duplicate archive URLs? */
	public static function is_duplicate_archive_path( $path ) {
		return (bool) preg_match( self::DUPLICATE_ARCHIVE, (string) $path );
	}

	public static function redirect_duplicate_archive() {
		$path = (string) wp_parse_url( isset( $_SERVER['REQUEST_URI'] ) ? wp_unslash( $_SERVER['REQUEST_URI'] ) : '', PHP_URL_PATH ); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		if ( ! self::is_duplicate_archive_path( $path ) ) {
			return;
		}

		// One show: its episode list. Several shows (or no list page): the home page, which links to every show.
		$target = home_url( '/' );
		$series = get_terms( array( 'taxonomy' => 'series', 'hide_empty' => true ) );
		if ( ! is_wp_error( $series ) && 1 === count( $series ) ) {
			$page = get_page_by_path( $series[0]->slug . '/episodes' );
			if ( $page ) {
				$target = get_permalink( $page );
			}
		}

		wp_safe_redirect( $target, 301 );
		exit;
	}

	/** Pure: is this request path an episode under the podcast plugin's own /podcast/<slug>/ URL? */
	public static function is_duplicate_episode_path( $path ) {
		return (bool) preg_match( self::DUPLICATE_EPISODE, (string) $path );
	}

	/** Pure: where /podcast/<slug>/ should go. An episode with no show has no other URL, so it stays put. */
	public static function duplicate_episode_target( $request_path, $permalink ) {
		if ( ! self::is_duplicate_episode_path( $request_path ) || ! $permalink ) {
			return null;
		}
		return self::is_duplicate_episode_path( (string) wp_parse_url( $permalink, PHP_URL_PATH ) ) ? null : $permalink;
	}

	public static function redirect_duplicate_episode() {
		if ( ! is_singular( 'podcast' ) ) {
			return;
		}

		$uri    = isset( $_SERVER['REQUEST_URI'] ) ? wp_unslash( $_SERVER['REQUEST_URI'] ) : ''; // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		$target = self::duplicate_episode_target( (string) wp_parse_url( $uri, PHP_URL_PATH ), get_permalink() );
		if ( ! $target ) {
			return;
		}

		$query = (string) wp_parse_url( $uri, PHP_URL_QUERY );
		wp_safe_redirect( '' === $query ? $target : $target . '?' . $query, 301 );
		exit;
	}

	/** Pure: does this REST route belong to the private set? */
	public static function is_private_route( $route ) {
		return (bool) preg_match( self::PRIVATE_ROUTES, (string) $route );
	}

	public static function guard_rest( $result, $server, $request ) {
		if ( ! is_user_logged_in() && self::is_private_route( $request->get_route() ) ) {
			return new WP_Error( 'rest_forbidden', 'Sorry, you are not allowed to do that.', array( 'status' => 401 ) );
		}
		return $result;
	}

	/** Pure given its inputs: is this user someone who has a public bio page? */
	public static function is_anchor( array $roles, $assignments, $published_episodes ) {
		return in_array( 'ng_talent', $roles, true ) || ! empty( $assignments ) || (int) $published_episodes > 0;
	}

	public static function maybe_404_author() {
		if ( ! is_author() ) {
			return;
		}

		$user = get_queried_object();
		if ( ! $user || empty( $user->ID ) ) {
			return;
		}

		$anchor = self::is_anchor(
			(array) $user->roles,
			Net_Gain_Talent_Assignments::list_for_user( $user->ID ),
			count_user_posts( $user->ID, 'podcast', true )
		);
		if ( $anchor ) {
			return;
		}

		global $wp_query;
		$wp_query->set_404();
		status_header( 404 );
		nocache_headers();
	}
}
