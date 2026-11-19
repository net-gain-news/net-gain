<?php
/**
 * Topics list (/{show}/topics/) and single topic (/{show}/topics/{slug}/) - see includes/class-topic-pages.php.
 * Drawn with the theme's header and footer. The header is the Net Gain Edtech Index page's own: the .page-hero block with the
 * accent-colour eyebrow line that doubles as the breadcrumb, the 44px headline, the intro paragraph and the stat boxes, then a
 * .page-body with the same section headings. The extra look comes from assets/internal-links.css; the filter, tabs and sort
 * from assets/topics.js (everything is complete HTML without it).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$ng_show      = Net_Gain_Topic_Pages::show_slug();
$ng_term      = $ng_show ? get_term_by( 'slug', $ng_show, 'series' ) : null;
$ng_show_name = $ng_term ? $ng_term->name : get_bloginfo( 'name' );
$ng_topic     = Net_Gain_Topic_Pages::current_topic();
$ng_all       = Net_Gain_Entities::topics( $ng_show );
$ng_page_all  = Net_Gain_Entities::page_topics( $ng_show );
$ng_index     = Net_Gain_Entities::index();
$ng_kinds     = Net_Gain_Entities::kinds();
$ng_blurbs    = Net_Gain_Entities::topic_blurbs();
$ng_shows_eps = array_filter(
	$ng_index,
	static function ( $e ) use ( $ng_show ) {
		return $e['show'] === $ng_show;
	}
);

/** The Index page's eyebrow style, reused for every crumb link. */
$ng_crumb_style = 'color:inherit;text-decoration:none';
$ng_eyebrow     = 'font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:var(--acl);margin-bottom:16px';
$ng_stat_label  = 'font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--mu);margin-bottom:8px';
$ng_stat_value  = 'font-size:36px;font-weight:700;letter-spacing:-0.02em';
$ng_section_bar = 'display:flex;align-items:baseline;justify-content:space-between;margin-bottom:24px;border-top:1px solid var(--bd);padding-top:24px';

function ng_tp_count_label( $n ) {
	return (int) $n . ' newscast' . ( 1 === (int) $n ? '' : 's' );
}

get_header();
?>

<?php if ( $ng_topic ) : ?>

	<?php
	$ng_kind_label = isset( $ng_kinds[ $ng_topic['kind'] ] ) ? $ng_kinds[ $ng_topic['kind'] ][0] : 'Topic';
	$ng_parent     = ( '' !== $ng_topic['parent'] && isset( $ng_all[ $ng_topic['parent'] ] ) ) ? $ng_all[ $ng_topic['parent'] ] : null;
	$ng_blurb      = $ng_blurbs[ $ng_topic['slug'] ] ?? '';
	$ng_children   = array();
	foreach ( $ng_topic['children'] as $ng_child_slug ) {
		if ( isset( $ng_page_all[ $ng_child_slug ] ) ) {
			$ng_children[] = $ng_page_all[ $ng_child_slug ];
		}
	}
	usort(
		$ng_children,
		static function ( $a, $b ) {
			return array( $b['count'], $a['name'] ) <=> array( $a['count'], $b['name'] );
		}
	);
	?>

	<div class="page-hero" style="padding:56px 40px 48px">
		<div class="mono" style="<?php echo esc_attr( $ng_eyebrow ); ?>">
			<a href="<?php echo esc_url( home_url( '/' . $ng_show . '/' ) ); ?>" style="<?php echo esc_attr( $ng_crumb_style ); ?>"><?php echo esc_html( $ng_show_name ); ?></a> &middot;
			<a href="<?php echo esc_url( Net_Gain_Entities::topics_index_url( $ng_show ) ); ?>" style="<?php echo esc_attr( $ng_crumb_style ); ?>">Topics</a> &middot;
			<?php echo esc_html( $ng_kind_label ); ?>
			<?php if ( $ng_parent && isset( $ng_page_all[ $ng_parent['slug'] ] ) ) : ?>
				in <a href="<?php echo esc_url( Net_Gain_Entities::topic_url( $ng_show, $ng_parent['slug'] ) ); ?>" style="<?php echo esc_attr( $ng_crumb_style ); ?>"><?php echo esc_html( $ng_parent['name'] ); ?></a>
			<?php elseif ( $ng_parent ) : ?>
				in <?php echo esc_html( $ng_parent['name'] ); ?>
			<?php endif; ?>
		</div>
		<h1 class="arch" style="font-weight:700;font-size:44px;letter-spacing:-0.03em;margin:0 0 16px;line-height:1.05"><?php echo esc_html( $ng_topic['name'] ); ?></h1>
		<p style="font-size:17px;color:var(--mu);max-width:680px;line-height:1.65;margin:0 0 36px">
			<?php if ( '' !== $ng_blurb ) : ?>
				<?php echo esc_html( $ng_blurb ); ?>
			<?php else : ?>
				<?php
				printf(
					'%1$s has come up in %2$s of %3$s since %4$s.',
					esc_html( $ng_topic['name'] ),
					esc_html( ng_tp_count_label( $ng_topic['count'] ) ),
					esc_html( $ng_show_name ),
					esc_html( mysql2date( 'F j, Y', $ng_topic['first'] ) )
				);
				?>
			<?php endif; ?>
			Each entry below links to the full newscast, with its transcript and source stories.
		</p>

		<div style="display:flex;gap:16px;flex-wrap:wrap">
			<div class="ng-stat-box">
				<div class="mono" style="<?php echo esc_attr( $ng_stat_label ); ?>">Newscasts</div>
				<div class="arch" style="<?php echo esc_attr( $ng_stat_value ); ?>"><?php echo (int) $ng_topic['count']; ?></div>
			</div>
			<div class="ng-stat-box">
				<div class="mono" style="<?php echo esc_attr( $ng_stat_label ); ?>">Last 30 days</div>
				<div class="arch" style="<?php echo esc_attr( $ng_stat_value ); ?>"><?php echo (int) $ng_topic['recent']; ?></div>
			</div>
			<div class="ng-stat-box" style="flex:2;min-width:200px">
				<div class="mono" style="<?php echo esc_attr( $ng_stat_label ); ?>">Latest</div>
				<div class="arch" style="font-size:22px;font-weight:700"><?php echo esc_html( mysql2date( 'M j, Y', $ng_topic['latest'] ) ); ?></div>
				<div class="mono" style="font-size:11px;color:var(--mu);margin-top:4px">First covered <?php echo esc_html( mysql2date( 'M j, Y', $ng_topic['first'] ) ); ?></div>
			</div>
		</div>
	</div>

	<div class="page-body ng-tp">

		<?php if ( $ng_children ) : ?>
			<div style="<?php echo esc_attr( $ng_section_bar ); ?>">
				<h2 class="arch" style="font-weight:700;font-size:20px;letter-spacing:-0.01em;margin:0">Places in <?php echo esc_html( $ng_topic['name'] ); ?></h2>
				<span class="mono" style="font-size:10px;color:var(--mu)"><?php echo (int) count( $ng_children ); ?> with their own page</span>
			</div>
			<div class="ng-topic-line" style="margin-bottom:40px">
				<?php foreach ( $ng_children as $ng_child ) : ?>
					<a class="ng-topic" href="<?php echo esc_url( Net_Gain_Entities::topic_url( $ng_show, $ng_child['slug'] ) ); ?>"><?php echo esc_html( $ng_child['name'] ); ?> <span class="ng-topic-count"><?php echo (int) $ng_child['count']; ?></span></a>
				<?php endforeach; ?>
			</div>
		<?php endif; ?>

		<?php
		// Topics that appear in the same newscasts (at least two shared) - the filter chips, and below the timeline, links to their pages.
		$ng_together = array();
		$ng_names    = array();
		foreach ( $ng_topic['episodes'] as $ng_id ) {
			if ( ! isset( $ng_index[ $ng_id ] ) ) {
				continue;
			}
			foreach ( $ng_index[ $ng_id ]['entities'] as $ng_tag ) {
				if ( $ng_tag['slug'] !== $ng_topic['slug'] && $ng_tag['slug'] !== $ng_topic['parent'] ) {
					$ng_together[ $ng_tag['slug'] ] = ( $ng_together[ $ng_tag['slug'] ] ?? 0 ) + 1;
					$ng_names[ $ng_tag['slug'] ]    = $ng_tag['name'];
				}
			}
		}
		arsort( $ng_together );
		$ng_refine = array_slice( array_filter( $ng_together, static function ( $n ) { return $n >= 2; } ), 0, 12, true );
		?>

		<div style="<?php echo esc_attr( $ng_section_bar ); ?>">
			<h2 class="arch" style="font-weight:700;font-size:20px;letter-spacing:-0.01em;margin:0">Coverage timeline</h2>
			<span class="mono ng-tp-shown" style="font-size:10px;color:var(--mu)" data-total="<?php echo (int) $ng_topic['count']; ?>"><?php echo esc_html( ng_tp_count_label( $ng_topic['count'] ) ); ?></span>
		</div>

		<?php if ( $ng_refine ) : ?>
			<div class="ng-refine" hidden>
				<span class="mono ng-related-label">Narrow to</span>
				<button type="button" class="ng-topic ng-filter is-on" data-tag="">All</button>
				<?php foreach ( $ng_refine as $ng_slug => $ng_n ) : ?>
					<button type="button" class="ng-topic ng-filter" data-tag="<?php echo esc_attr( $ng_slug ); ?>"><?php echo esc_html( $ng_names[ $ng_slug ] ); ?> <span class="ng-topic-count"><?php echo (int) $ng_n; ?></span></button>
				<?php endforeach; ?>
			</div>
		<?php endif; ?>

		<?php
		$ng_months = array();
		foreach ( $ng_topic['episodes'] as $ng_id ) {
			if ( isset( $ng_index[ $ng_id ] ) ) {
				$ng_months[ substr( $ng_index[ $ng_id ]['date'], 0, 7 ) ][] = $ng_id;
			}
		}
		$ng_shown = 0;
		?>
		<div class="ng-timeline-wrap">
			<?php foreach ( $ng_months as $ng_month => $ng_ids ) : ?>
				<?php $ng_open = $ng_shown < 10; $ng_shown += count( $ng_ids ); ?>
				<details class="ng-month"<?php echo $ng_open ? ' open' : ''; ?>>
					<summary class="mono"><span><?php echo esc_html( mysql2date( 'F Y', $ng_month . '-01' ) ); ?></span> <span class="ng-month-count"><?php echo esc_html( ng_tp_count_label( count( $ng_ids ) ) ); ?></span></summary>
					<ol class="ng-timeline">
						<?php foreach ( $ng_ids as $ng_id ) : ?>
							<?php
							$ng_entry = $ng_index[ $ng_id ];
							$ng_note  = isset( $ng_topic['notes'][ $ng_id ] ) ? $ng_topic['notes'][ $ng_id ] : '';
							$ng_via   = isset( $ng_topic['via'][ $ng_id ] ) ? $ng_topic['via'][ $ng_id ] : '';
							$ng_tags  = array();
							foreach ( $ng_entry['entities'] as $ng_tag ) {
								$ng_tags[] = $ng_tag['slug'];
							}
							?>
							<li data-tags="<?php echo esc_attr( implode( ' ', $ng_tags ) ); ?>">
								<div class="mono ng-timeline-date"><?php echo esc_html( mysql2date( 'M j, Y', $ng_entry['date'] ) ); ?></div>
								<div>
									<a class="arch ng-timeline-title" href="<?php echo esc_url( $ng_entry['url'] ); ?>"><?php echo esc_html( $ng_entry['title'] ); ?></a>
									<?php if ( '' !== $ng_note ) : ?>
										<p class="ng-timeline-note"><?php echo ( '' !== $ng_via ) ? '<span class="mono ng-via">' . esc_html( $ng_via ) . '</span> ' : ''; // phpcs:ignore WordPress.Security.EscapeOutput -- escaped above ?><?php echo esc_html( $ng_note ); ?></p>
									<?php endif; ?>
									<div class="mono ng-timeline-actions">
										<a href="<?php echo esc_url( add_query_arg( 'autoplay', '1', $ng_entry['url'] ) ); ?>">&#9658; Listen</a>
										<a href="<?php echo esc_url( $ng_entry['url'] . '#transcript' ); ?>">Transcript</a>
									</div>
								</div>
							</li>
						<?php endforeach; ?>
					</ol>
				</details>
			<?php endforeach; ?>
		</div>

		<?php
		$ng_links = array();
		foreach ( $ng_together as $ng_slug => $ng_n ) {
			if ( $ng_n >= 2 && isset( $ng_page_all[ $ng_slug ] ) ) {
				$ng_links[] = $ng_page_all[ $ng_slug ];
			}
			if ( count( $ng_links ) >= 8 ) {
				break;
			}
		}
		?>
		<?php if ( $ng_links ) : ?>
			<div style="<?php echo esc_attr( $ng_section_bar ); ?>;margin-top:48px">
				<h2 class="arch" style="font-weight:700;font-size:20px;letter-spacing:-0.01em;margin:0">Often covered together</h2>
			</div>
			<div class="ng-topic-line">
				<?php foreach ( $ng_links as $ng_other ) : ?>
					<a class="ng-topic" href="<?php echo esc_url( Net_Gain_Entities::topic_url( $ng_show, $ng_other['slug'] ) ); ?>"><?php echo esc_html( $ng_other['name'] ); ?></a>
				<?php endforeach; ?>
			</div>
		<?php endif; ?>

		<p class="mono ng-related-more" style="margin-top:44px">
			<a href="<?php echo esc_url( Net_Gain_Entities::topics_index_url( $ng_show ) ); ?>">&larr; All topics</a>
			<a href="<?php echo esc_url( home_url( '/' . $ng_show . '/episodes/' ) ); ?>">All newscasts &rarr;</a>
		</p>
	</div>

<?php else : ?>

	<?php
	$ng_latest_date = '';
	foreach ( $ng_shows_eps as $ng_e ) {
		$ng_latest_date = $ng_e['date'];
		break;
	}

	// Page-worthy topics by kind. Places nest: a place whose parent also has a page sits under that parent.
	$ng_by_kind = array_fill_keys( array_keys( $ng_kinds ), array() );
	foreach ( $ng_page_all as $ng_t ) {
		$ng_by_kind[ $ng_t['kind'] ][ $ng_t['slug'] ] = $ng_t;
	}
	$ng_place_children = array();
	$ng_place_top      = array();
	foreach ( $ng_by_kind['place'] as $ng_slug => $ng_t ) {
		if ( '' !== $ng_t['parent'] && isset( $ng_by_kind['place'][ $ng_t['parent'] ] ) ) {
			$ng_place_children[ $ng_t['parent'] ][] = $ng_t;
		} else {
			$ng_place_top[ $ng_slug ] = $ng_t;
		}
	}
	$ng_by_kind['place'] = $ng_place_top;

	// Trending: the most covered in the last 30 days.
	$ng_trending = array_filter( $ng_page_all, static function ( $t ) { return $t['recent'] >= 2; } );
	uasort( $ng_trending, static function ( $a, $b ) { return array( $b['recent'], $b['count'] ) <=> array( $a['recent'], $a['count'] ); } );
	$ng_trending = array_slice( $ng_trending, 0, 8, true );

	/** One list row; places pass their children. */
	$ng_item = static function ( $t, $children = array(), $extra = false ) use ( $ng_show, $ng_blurbs ) {
		$out  = '<li class="ng-tp-item' . ( $extra ? ' ng-tp-extra' : '' ) . '" data-name="' . esc_attr( strtolower( $t['name'] ) ) . '" data-count="' . (int) $t['count'] . '" data-latest="' . esc_attr( $t['latest'] ) . '" data-recent="' . (int) $t['recent'] . '">';
		$out .= '<a class="ng-tp-name" href="' . esc_url( Net_Gain_Entities::topic_url( $ng_show, $t['slug'] ) ) . '">' . esc_html( $t['name'] ) . '</a>';
		$out .= '<span class="mono ng-tp-meta">' . esc_html( ng_tp_count_label( $t['count'] ) ) . ' &middot; latest ' . esc_html( mysql2date( 'M j', $t['latest'] ) ) . '</span>';
		if ( isset( $ng_blurbs[ $t['slug'] ] ) ) {
			$out .= '<span class="ng-tp-blurb">' . esc_html( $ng_blurbs[ $t['slug'] ] ) . '</span>';
		}
		if ( $children ) {
			usort( $children, static function ( $a, $b ) { return array( $b['count'], $a['name'] ) <=> array( $a['count'], $b['name'] ); } );
			$out .= '<ul class="ng-tp-children">';
			foreach ( $children as $child ) {
				$out .= '<li class="ng-tp-item ng-tp-child" data-name="' . esc_attr( strtolower( $child['name'] ) ) . '" data-count="' . (int) $child['count'] . '" data-latest="' . esc_attr( $child['latest'] ) . '" data-recent="' . (int) $child['recent'] . '">'
					. '<a class="ng-tp-name" href="' . esc_url( Net_Gain_Entities::topic_url( $ng_show, $child['slug'] ) ) . '">' . esc_html( $child['name'] ) . '</a>'
					. '<span class="mono ng-tp-meta">' . esc_html( ng_tp_count_label( $child['count'] ) ) . '</span></li>';
			}
			$out .= '</ul>';
		}
		return $out . '</li>';
	};
	?>

	<div class="page-hero" style="padding:56px 40px 48px">
		<div class="mono" style="<?php echo esc_attr( $ng_eyebrow ); ?>">
			<a href="<?php echo esc_url( home_url( '/' . $ng_show . '/' ) ); ?>" style="<?php echo esc_attr( $ng_crumb_style ); ?>"><?php echo esc_html( $ng_show_name ); ?></a> &middot; Topics
		</div>
		<h1 class="arch" style="font-weight:700;font-size:44px;letter-spacing:-0.03em;margin:0 0 16px;line-height:1.05">Topics</h1>
		<p style="font-size:17px;color:var(--mu);max-width:680px;line-height:1.65;margin:0 0 36px">The companies, organizations, places and issues <?php echo esc_html( $ng_show_name ); ?> covers in K&#8209;12 education technology, security and policy. Pick one to see every newscast that covered it, newest first, with what we reported each time.</p>
		<div style="display:flex;gap:16px;flex-wrap:wrap">
			<div class="ng-stat-box">
				<div class="mono" style="<?php echo esc_attr( $ng_stat_label ); ?>">Topic pages</div>
				<div class="arch" style="<?php echo esc_attr( $ng_stat_value ); ?>"><?php echo (int) count( $ng_page_all ); ?></div>
			</div>
			<div class="ng-stat-box">
				<div class="mono" style="<?php echo esc_attr( $ng_stat_label ); ?>">Newscasts</div>
				<div class="arch" style="<?php echo esc_attr( $ng_stat_value ); ?>"><?php echo (int) count( $ng_shows_eps ); ?></div>
			</div>
			<div class="ng-stat-box" style="flex:2;min-width:200px">
				<div class="mono" style="<?php echo esc_attr( $ng_stat_label ); ?>">Latest newscast</div>
				<div class="arch" style="font-size:22px;font-weight:700"><?php echo '' !== $ng_latest_date ? esc_html( mysql2date( 'M j, Y', $ng_latest_date ) ) : '&mdash;'; ?></div>
				<div class="mono" style="font-size:11px;color:var(--mu);margin-top:4px">A topic gets its own page after it has been covered in three newscasts</div>
			</div>
		</div>
	</div>

	<div class="page-body ng-tp">

		<?php if ( $ng_trending ) : ?>
			<div style="<?php echo esc_attr( $ng_section_bar ); ?>">
				<h2 class="arch" style="font-weight:700;font-size:20px;letter-spacing:-0.01em;margin:0">Trending this month</h2>
				<span class="mono" style="font-size:10px;color:var(--mu)">Most newscasts in the last 30 days</span>
			</div>
			<div class="ng-topic-line" style="margin-bottom:44px">
				<?php foreach ( $ng_trending as $ng_t ) : ?>
					<a class="ng-topic" href="<?php echo esc_url( Net_Gain_Entities::topic_url( $ng_show, $ng_t['slug'] ) ); ?>"><?php echo esc_html( $ng_t['name'] ); ?> <span class="ng-topic-count"><?php echo (int) $ng_t['recent']; ?></span></a>
				<?php endforeach; ?>
			</div>
		<?php endif; ?>

		<div class="ng-tp-controls" hidden>
			<input type="search" class="ng-tp-q" placeholder="Search topics, companies, places" aria-label="Search topics, companies and places" autocomplete="off">
			<div class="ng-tp-tabs" role="group" aria-label="Show">
				<button type="button" class="ng-topic ng-tp-tab is-on" data-kind="all">All <span class="ng-topic-count"><?php echo (int) count( $ng_page_all ); ?></span></button>
				<?php foreach ( $ng_kinds as $ng_kind => $ng_label ) : ?>
					<?php if ( $ng_by_kind[ $ng_kind ] || ( 'place' === $ng_kind && $ng_place_children ) ) : ?>
						<button type="button" class="ng-topic ng-tp-tab" data-kind="<?php echo esc_attr( $ng_kind ); ?>"><?php echo esc_html( $ng_label[1] ); ?> <span class="ng-topic-count"><?php echo (int) count( array_filter( $ng_page_all, static function ( $t ) use ( $ng_kind ) { return $t['kind'] === $ng_kind; } ) ); ?></span></button>
					<?php endif; ?>
				<?php endforeach; ?>
			</div>
			<label class="mono ng-tp-sortlabel">Sort
				<select class="ng-tp-sort" aria-label="Sort">
					<option value="count">Most covered</option>
					<option value="recent">Most recent</option>
					<option value="name">A to Z</option>
				</select>
			</label>
			<span class="mono ng-tp-status" aria-live="polite"></span>
		</div>

		<?php foreach ( $ng_kinds as $ng_kind => $ng_label ) : ?>
			<?php
			$ng_list = $ng_by_kind[ $ng_kind ];
			if ( ! $ng_list ) {
				continue;
			}
			$ng_total_kind = count( array_filter( $ng_page_all, static function ( $t ) use ( $ng_kind ) { return $t['kind'] === $ng_kind; } ) );
			?>
			<section class="ng-tp-section" data-kind="<?php echo esc_attr( $ng_kind ); ?>" id="<?php echo esc_attr( sanitize_title( $ng_label[1] ) ); ?>">
				<div style="<?php echo esc_attr( $ng_section_bar ); ?>">
					<h2 class="arch" style="font-weight:700;font-size:20px;letter-spacing:-0.01em;margin:0"><?php echo esc_html( $ng_label[1] ); ?></h2>
					<span class="mono" style="font-size:10px;color:var(--mu)"><?php echo (int) $ng_total_kind; ?></span>
				</div>
				<ul class="ng-tp-list<?php echo 'topic' === $ng_kind ? ' ng-tp-cards' : ''; ?>">
					<?php
					$ng_n = 0;
					foreach ( $ng_list as $ng_t ) {
						$ng_n++;
						$ng_children_of = 'place' === $ng_kind ? ( $ng_place_children[ $ng_t['slug'] ] ?? array() ) : array();
						echo $ng_item( $ng_t, $ng_children_of, 'topic' !== $ng_kind && $ng_n > 24 ); // phpcs:ignore WordPress.Security.EscapeOutput -- built and escaped in the closure above
					}
					?>
				</ul>
				<?php if ( 'topic' !== $ng_kind && count( $ng_list ) > 24 ) : ?>
					<button type="button" class="mono ng-tp-showall" hidden>Show all <?php echo (int) count( $ng_list ); ?></button>
				<?php endif; ?>
			</section>
		<?php endforeach; ?>

		<?php if ( ! $ng_page_all ) : ?>
			<p class="ng-topic-intro">Topics appear here once they have come up in several newscasts.</p>
		<?php endif; ?>

		<p class="mono ng-related-more" style="margin-top:44px"><a href="<?php echo esc_url( home_url( '/' . $ng_show . '/episodes/' ) ); ?>">All newscasts &rarr;</a></p>
	</div>

<?php endif; ?>

<?php get_footer(); ?>
