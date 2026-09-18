<?php
/**
 * Custom permalink structure for Seriously Simple Podcasting's `podcast` CPT.
 * Read directly from SSP's own source (class-cpt-podcast-handler.php) before
 * building this: its rewrite is a single flat slug, NOT nested under its own
 * `series` taxonomy. This filter + rule is what actually produces
 * /{show-slug}/{episode}/ rather than relying on something SSP doesn't do
 * natively.
 *
 * URL structure (revised 2026-09-18, see SPEC.md §6.2): each show lives at a
 * bare top-level slug - /edtech/, /edtech/{episode-slug}/ - not nested under
 * /shows/. The /shows/ path is reserved for the separate cross-show hub page
 * (SPEC.md §6.2's "all our shows" internal-linking page), which is an
 * ordinary WordPress Page, not something this class touches.
 *
 * The episode-matching pattern is restricted to registered show slugs
 * (queried from `ng_show`) rather than an unqualified `([^/]+)/([^/]+)/?$` -
 * a blanket two-segment wildcard would also swallow every show's own child
 * pages (episodes/index/subscribe/welcome, each a normal Page one level
 * under the show's page).
 *
 * Registered at 'top' priority, deliberately, with the four reserved child-
 * page slugs excluded via negative lookahead. An earlier version of this
 * class tried 'bottom' priority instead, reasoning that WordPress's own page
 * rules would then be checked first - that's wrong: WordPress does not
 * generate a specific rewrite rule per existing page. Every page (at any
 * depth) is caught by ONE generic, low-priority pattern
 * (`(.?.+?)(?:/([0-9]+))?/?$` -> `pagename`) that WordPress registers last.
 * At 'bottom' priority our rule sits even later than that catch-all, which
 * always matches a two-segment path first and 404s before our rule is ever
 * tried - confirmed live via `wp rewrite list`. Hence 'top' + an explicit
 * exclusion list, rather than relying on rule ordering to defer to pages.
 *
 * Deploy note: adding/changing add_rewrite_rule() calls doesn't retroactively
 * update WordPress's cached compiled rewrite rules on an already-active
 * install - a flush (Settings -> Permalinks -> Save, or deactivate/reactivate
 * this plugin) is required once after deploying this file.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Website_Rewrite {

	/**
	 * Every show gets these same child pages (see the design handoff's site
	 * map) - reserved so they never get mistaken for an episode's post_name.
	 */
	const RESERVED_CHILD_SLUGS = array( 'episodes', 'index', 'subscribe', 'welcome' );

	public static function register() {
		add_filter( 'post_type_link', array( __CLASS__, 'filter_permalink' ), 10, 2 );
		add_action( 'init', array( __CLASS__, 'add_rewrite_rules' ) );
	}

	public static function filter_permalink( $post_link, $post ) {
		if ( 'podcast' !== $post->post_type ) {
			return $post_link;
		}

		$terms = get_the_terms( $post->ID, 'series' );
		if ( empty( $terms ) || is_wp_error( $terms ) ) {
			return $post_link;
		}

		return home_url( "/{$terms[0]->slug}/{$post->post_name}/" );
	}

	public static function add_rewrite_rules() {
		$show_slugs = self::get_show_slugs();
		if ( empty( $show_slugs ) ) {
			return;
		}

		$show_pattern    = implode( '|', array_map( 'preg_quote', $show_slugs ) );
		$reserved_lookahead = implode( '|', array_map( 'preg_quote', self::RESERVED_CHILD_SLUGS ) );
		$pattern = "^({$show_pattern})/(?!(?:{$reserved_lookahead})/?$)([^/]+)/?\$";

		// Matched purely on the episode's own post_name (WordPress already enforces
		// post_name uniqueness within a post type) - the show-slug segment makes the
		// URL readable but isn't itself re-validated against the episode's series.
		// The negative lookahead defers to a show's own reserved child pages
		// (RESERVED_CHILD_SLUGS) - see the class docblock for why 'top' priority
		// plus this exclusion is used instead of rule ordering.
		add_rewrite_rule(
			$pattern,
			'index.php?post_type=podcast&name=$matches[2]',
			'top'
		);
	}

	/**
	 * Slugs of every registered show - these are the only first-path-segments
	 * this class's rewrite rule matches against.
	 */
	private static function get_show_slugs() {
		$show_ids = get_posts( array(
			'post_type'      => 'ng_show',
			'post_status'    => 'publish',
			'posts_per_page' => -1,
			'fields'         => 'ids',
		) );

		$slugs = array();
		foreach ( $show_ids as $show_id ) {
			$slug = get_post_field( 'post_name', $show_id );
			if ( $slug ) {
				$slugs[] = $slug;
			}
		}

		return $slugs;
	}
}
