<?php
/**
 * Google News sitemap at /news-sitemap.xml (2026-10-09), episodes only.
 *
 * AIOSEO's own News Sitemap is a separate add-on that this site's licence tier does not include, so the plugin
 * serves the file itself. Per Google's news sitemap format it lists only articles published in the last two days
 * (up to 1000), each with its publication name, language, publication date and title. There is ONE sitemap for the
 * whole site and the publication is the site's name ("Net Gain News") for every show: Google News keys a publication
 * to the website and names it from the site name, so this must agree with the site name and the publisher in each
 * episode's NewsArticle structured data (class-news-schema.php). Blog posts and pages are never listed.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_News_Sitemap {

	const PATH        = 'news-sitemap.xml';
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
		if ( self::PATH !== trim( $path, '/' ) ) {
			return;
		}

		$posts = get_posts(
			array(
				'post_type'      => 'podcast',
				'post_status'    => 'publish',
				'posts_per_page' => self::MAX_URLS,
				'orderby'        => 'date',
				'order'          => 'DESC',
				'date_query'     => array( array( 'after' => self::WINDOW_DAYS . ' days ago', 'inclusive' => true ) ),
			)
		);

		// One sitemap, one publication: the site's own name, for every show.
		$publication = html_entity_decode( get_bloginfo( 'name' ), ENT_QUOTES, 'UTF-8' );
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
