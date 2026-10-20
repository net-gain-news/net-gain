<?php
/**
 * Google News sitemaps, one per show, at /news-sitemap-{show-slug}.xml (e.g. /news-sitemap-edtech.xml), episodes only.
 *
 * AIOSEO's own News Sitemap is a separate add-on that this site's licence tier does not include, so the plugin
 * serves the files itself. Per Google's news sitemap format each lists only articles published in the last two days
 * (up to 1000), each with its publication name, language, publication date and title. Every show is its own
 * publication in Google Publisher Center (2026-10-20: "Net Gain Edtech", scoped to /edtech, under the "Net Gain News"
 * organization), and Google requires news:name to match that publication's name exactly, so a show's sitemap names
 * the show (its 'series' term name). Onboarding a show means registering its publication in Publisher Center and
 * submitting its /news-sitemap-{slug}.xml in Search Console. The structured-data publisher stays the organization
 * (class-news-schema.php). Blog posts and pages are never listed.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_News_Sitemap {

	// Sitemap paths Search Console still lists that must answer 410 Gone (2026-10-20): the single site-wide news file
	// this replaced, and AIOSEO's optional RSS sitemap, which this site does not use. Enabling that AIOSEO feature
	// would need sitemap.rss taken off this list, since this handler runs first.
	const GONE_PATHS  = array( 'news-sitemap.xml', 'sitemap.rss' );
	const WINDOW_DAYS = 2;
	const MAX_URLS    = 1000;

	public static function register() {
		// Priority 1: AIOSEO's own sitemap request parser (parse_request, priority 10) answers every "*-sitemap.xml"
		// request it cannot serve with a 404 and exits, so this has to get in first. No rewrite rule is needed.
		add_action( 'parse_request', array( __CLASS__, 'maybe_serve' ), 1 );
	}

	public static function maybe_serve( $wp = null ) {
		$path = isset( $wp->request ) ? (string) $wp->request : '';
		if ( '' === $path && isset( $_SERVER['REQUEST_URI'] ) ) {
			$path = (string) wp_parse_url( wp_unslash( $_SERVER['REQUEST_URI'] ), PHP_URL_PATH ); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		}
		$path = trim( $path, '/' );
		if ( in_array( $path, self::GONE_PATHS, true ) ) {
			status_header( 410 );
			header( 'X-Robots-Tag: noindex' );
			exit;
		}
		$slug = self::show_slug( $path );
		if ( '' === $slug ) {
			return;
		}
		$term = get_term_by( 'slug', $slug, 'series' );
		if ( ! $term ) {
			return;    // not a show: leave it to the normal 404 handling
		}

		$posts = get_posts(
			array(
				'post_type'      => 'podcast',
				'post_status'    => 'publish',
				'posts_per_page' => self::MAX_URLS,
				'orderby'        => 'date',
				'order'          => 'DESC',
				'date_query'     => array( array( 'after' => self::WINDOW_DAYS . ' days ago', 'inclusive' => true ) ),
				'tax_query'      => array( array( 'taxonomy' => 'series', 'field' => 'term_id', 'terms' => $term->term_id ) ),
			)
		);

		// One sitemap, one publication: this show's own name.
		$publication = html_entity_decode( $term->name, ENT_QUOTES, 'UTF-8' );
		$items       = array();
		foreach ( $posts as $post ) {
			$items[] = array(
				'loc'      => get_permalink( $post ),
				'name'     => $publication,
				'language' => 'en',
				'date'     => get_post_time( 'c', false, $post ),
				'title'    => get_the_title( $post ),
			);
		}

		status_header( 200 );
		header( 'Content-Type: text/xml; charset=UTF-8' );              // the same headers AIOSEO sends with its own sitemaps
		header( 'X-Robots-Tag: noindex, follow' );                     // the sitemap file itself, as is usual; the URLs inside are what get indexed
		echo self::build_xml( $items ); // phpcs:ignore WordPress.Security.EscapeOutput -- escaped in build_xml
		exit;
	}

	/** Pure: 'news-sitemap-edtech.xml' -> 'edtech'; '' for any other path. */
	public static function show_slug( $path ) {
		return preg_match( '/^news-sitemap-([a-z0-9][a-z0-9-]*)\.xml$/', (string) $path, $m ) ? $m[1] : '';
	}

	/** Pure: items = list of array(loc, name, language, date, title) -> the sitemap document. */
	public static function build_xml( array $items ) {
		$esc = function ( $text ) {
			return htmlspecialchars( (string) $text, ENT_XML1 | ENT_QUOTES, 'UTF-8' );
		};

		$xml  = '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
		$xml .= '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">' . "\n";
		foreach ( $items as $item ) {
			$xml .= "\t<url>\n";
			$xml .= "\t\t<loc>" . $esc( $item['loc'] ) . "</loc>\n";
			$xml .= "\t\t<news:news>\n";
			$xml .= "\t\t\t<news:publication>\n";
			$xml .= "\t\t\t\t<news:name>" . $esc( $item['name'] ) . "</news:name>\n";
			$xml .= "\t\t\t\t<news:language>" . $esc( $item['language'] ) . "</news:language>\n";
			$xml .= "\t\t\t</news:publication>\n";
			$xml .= "\t\t\t<news:publication_date>" . $esc( $item['date'] ) . "</news:publication_date>\n";
			$xml .= "\t\t\t<news:title>" . $esc( $item['title'] ) . "</news:title>\n";
			$xml .= "\t\t</news:news>\n";
			$xml .= "\t</url>\n";
		}
		$xml .= "</urlset>\n";
		return $xml;
	}
}
